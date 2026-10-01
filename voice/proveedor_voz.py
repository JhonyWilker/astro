from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import wave
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

from voice.hablar import InformeSintesis, inspeccionar_wav, sintetizar


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_CONFIG = RAIZ_PROYECTO / "config" / "config.yaml"
RUTA_USO = RAIZ_PROYECTO / "logs" / "voz.jsonl"


class ErrorElevenLabs(RuntimeError):
    """Fallo seguro de la síntesis remota, sin incluir credenciales."""


@dataclass(frozen=True)
class ConfiguracionVoz:
    proveedor: str
    respaldo: str
    cambio_automatico: bool
    voice_id: str
    modelo: str
    formato: str
    frecuencia_hz: int
    timeout_segundos: float
    clave_entorno: str
    base_url: str
    estabilidad: float
    similitud: float
    formato_streaming: str = "pcm_16000"
    frecuencia_streaming_hz: int = 16000


@dataclass(frozen=True)
class BloquePCM:
    """Audio incremental o una frontera reproducida de un fragmento."""

    datos: bytes
    confirmado: int | None = None
    fin_fragmento: bool = False


def cargar_configuracion_voz(ruta: Path = RUTA_CONFIG) -> ConfiguracionVoz:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, dict) or not isinstance(datos.get("voz"), dict):
        raise ValueError("Falta la sección 'voz' en config/config.yaml")
    voz = datos["voz"]
    nube = voz.get("elevenlabs")
    if not isinstance(nube, dict):
        raise ValueError("Falta la configuración de ElevenLabs")

    configuracion = ConfiguracionVoz(
        proveedor=str(voz.get("proveedor", "")),
        respaldo=str(voz.get("respaldo", "")),
        cambio_automatico=voz.get("cambio_automatico") is True,
        voice_id=str(nube.get("voice_id", "")),
        modelo=str(nube.get("modelo", "")),
        formato=str(nube.get("formato", "")),
        frecuencia_hz=int(nube.get("frecuencia_hz", 0)),
        timeout_segundos=float(nube.get("timeout_segundos", 0)),
        clave_entorno=str(nube.get("clave_entorno", "")),
        base_url=str(nube.get("base_url", "")),
        estabilidad=float(nube.get("estabilidad", -1)),
        similitud=float(nube.get("similitud", -1)),
        formato_streaming=str(nube.get("formato_streaming", "pcm_16000")),
        frecuencia_streaming_hz=int(nube.get("frecuencia_streaming_hz", 16000)),
    )
    _validar_configuracion(configuracion)
    return configuracion


def _validar_configuracion(configuracion: ConfiguracionVoz) -> None:
    if configuracion.proveedor != "elevenlabs":
        raise ValueError("El proveedor de voz debe ser 'elevenlabs'")
    if configuracion.respaldo != "piper":
        raise ValueError("El respaldo de voz debe ser 'piper'")
    if not configuracion.cambio_automatico:
        raise ValueError("El cambio automático de voz debe estar activo")
    if not configuracion.voice_id:
        raise ValueError("Falta voice_id en la configuración de voz")
    if configuracion.modelo not in {"eleven_v4", "eleven_v4_turbo"}:
        raise ValueError(
            "La voz expresiva de ASTRO requiere eleven_v4 o eleven_v4_turbo"
        )
    if configuracion.formato != f"pcm_{configuracion.frecuencia_hz}":
        raise ValueError("El formato PCM no coincide con su frecuencia")
    if configuracion.frecuencia_hz not in {16000, 22050, 24000}:
        raise ValueError("Frecuencia PCM no admitida")
    if (
        configuracion.formato_streaming
        != f"pcm_{configuracion.frecuencia_streaming_hz}"
    ):
        raise ValueError("El formato PCM de streaming no coincide con su frecuencia")
    if configuracion.frecuencia_streaming_hz != 16000:
        raise ValueError("El streaming con AEC3 debe usar PCM a 16 kHz")
    if configuracion.timeout_segundos <= 0:
        raise ValueError("timeout_segundos debe ser positivo")
    if not configuracion.clave_entorno:
        raise ValueError("Falta clave_entorno en la configuración de voz")
    if not configuracion.base_url.startswith("https://"):
        raise ValueError("base_url de voz debe usar HTTPS")
    if not 0 <= configuracion.estabilidad <= 1:
        raise ValueError("estabilidad debe estar entre 0 y 1")
    if not 0 <= configuracion.similitud <= 1:
        raise ValueError("similitud debe estar entre 0 y 1")


EXPRESION_NEUTRA = "neutral, natural, understated"
PATRON_DIRECCION = re.compile(r"[A-Za-z][A-Za-z ,'-]{2,119}")
EFECTOS_NO_VOCALES = {
    "applause", "explosion", "gunshot", "music", "sing", "singing",
    "sound effect", "thunder", "whistle", "whistling",
}
AVISO_PIPER_CREDITOS = (
    "Jhony, estoy usando la voz local Piper porque ElevenLabs "
    "se ha quedado sin créditos."
)
AVISO_PIPER_FALLO = (
    "Jhony, estoy usando la voz local Piper porque ElevenLabs "
    "no está disponible."
)


def normalizar_direccion_voz(direccion: str | None) -> str:
    """Acepta matices abiertos, pero únicamente como dirección vocal."""
    if not isinstance(direccion, str):
        return EXPRESION_NEUTRA
    candidata = " ".join(direccion.strip(" []").split())
    if not PATRON_DIRECCION.fullmatch(candidata):
        return EXPRESION_NEUTRA
    normalizada = candidata.casefold()
    if any(efecto in normalizada for efecto in EFECTOS_NO_VOCALES):
        return EXPRESION_NEUTRA
    return candidata


def motivo_respaldo_voz(error: BaseException | str | None) -> str:
    """Clasifica el fallo sin conservar mensajes sensibles del proveedor."""
    detalle = str(error or "").casefold()
    indicadores_creditos = (
        "credit",
        "quota",
        "character_limit",
        "insufficient",
        "payment_required",
        "resource_exhausted",
    )
    if any(indicador in detalle for indicador in indicadores_creditos):
        return "creditos"
    return "fallo"


def preparar_texto_expresivo(
    texto: str,
    direccion: str | None = None,
) -> str:
    texto_limpio = re.sub(r"\[([^\]]*)\]", r"(\1)", texto).strip()
    texto_limpio = re.sub(r"(?<=\w),(?=\s)", "", texto_limpio)
    if not texto_limpio:
        raise ValueError("El texto no puede estar vacío")
    expresion = normalizar_direccion_voz(direccion)
    return f"[{expresion}] {texto_limpio}"


def preparar_continuacion_voz(texto: str) -> str:
    """Limpia un fragmento que continúa dentro del mismo turno vocal."""
    texto_limpio = re.sub(r"\[([^\]]*)\]", r"(\1)", texto).strip()
    texto_limpio = re.sub(r"(?<=\w),(?=\s)", "", texto_limpio)
    if not texto_limpio:
        raise ValueError("El texto no puede estar vacío")
    return texto_limpio


def sintetizar_elevenlabs(
    texto: str,
    clave: str,
    configuracion: ConfiguracionVoz,
    salida: Path,
    *,
    abrir: Callable[..., Any] = urlopen,
    reloj: Callable[[], float] = perf_counter,
) -> InformeSintesis:
    texto = texto.strip()
    if not texto:
        raise ValueError("El texto no puede estar vacío")
    if not clave:
        raise ErrorElevenLabs("Falta la clave de ElevenLabs")

    cuerpo = json.dumps(
        {
            "text": texto,
            "model_id": configuracion.modelo,
            "language_code": "es",
            "voice_settings": {
                "stability": configuracion.estabilidad,
                "similarity_boost": configuracion.similitud,
            },
        }
    ).encode("utf-8")
    url = (
        f"{configuracion.base_url.rstrip('/')}/v1/text-to-speech/"
        f"{quote(configuracion.voice_id, safe='')}"
        f"?output_format={configuracion.formato}"
    )
    peticion = Request(
        url,
        data=cuerpo,
        method="POST",
        headers={
            "Accept": "application/octet-stream",
            "Content-Type": "application/json",
            "xi-api-key": clave,
        },
    )

    inicio = reloj()
    respuesta: Any | None = None
    try:
        respuesta = abrir(peticion, timeout=configuracion.timeout_segundos)
        audio = respuesta.read()
    except HTTPError as error:
        raise ErrorElevenLabs(
            f"ElevenLabs respondió HTTP {error.code}"
        ) from error
    except (TimeoutError, URLError, OSError) as error:
        raise ErrorElevenLabs("No se pudo conectar con ElevenLabs") from error
    finally:
        cerrar = getattr(respuesta, "close", None)
        if cerrar is not None:
            cerrar()

    if not audio or len(audio) % 2:
        raise ErrorElevenLabs("ElevenLabs devolvió PCM inválido")

    salida.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(salida), "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(configuracion.frecuencia_hz)
        archivo.writeframes(audio)
    return inspeccionar_wav(salida, reloj() - inicio)


def registrar_uso_voz(
    texto: str,
    proveedor: str,
    resultado: str,
    *,
    respaldo: bool,
    error: str | None = None,
    caracteres_enviados: int | None = None,
    ruta: Path = RUTA_USO,
) -> None:
    registro = {
        "fecha": datetime.now(timezone.utc).isoformat(),
        "proveedor": proveedor,
        "caracteres": len(texto),
        "resultado": resultado,
        "respaldo": respaldo,
    }
    if caracteres_enviados is not None:
        registro["caracteres_enviados"] = caracteres_enviados
    if error is not None:
        registro["error"] = error
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")


class SintetizadorConRespaldo:
    def __init__(
        self,
        configuracion: ConfiguracionVoz,
        clave: str,
        voz_piper: Any,
        configuracion_piper: Any,
        *,
        sintetizador_nube: Callable[..., InformeSintesis] = sintetizar_elevenlabs,
        sintetizador_local: Callable[..., InformeSintesis] = sintetizar,
        registrador: Callable[..., None] = registrar_uso_voz,
    ) -> None:
        self.configuracion = configuracion
        self.clave = clave
        self.voz_piper = voz_piper
        self.configuracion_piper = configuracion_piper
        self.sintetizador_nube = sintetizador_nube
        self.sintetizador_local = sintetizador_local
        self.registrador = registrador
        self._proveedor_activo = "elevenlabs"

    @property
    def principal_disponible(self) -> bool:
        return bool(self.clave)

    @property
    def streaming_disponible(self) -> bool:
        return bool(self.clave) and self.configuracion.modelo.startswith("eleven_v4")

    async def producir_streaming(
        self,
        cola_texto: asyncio.Queue[Any],
        cola_audio: Any,
        ruta_base: Path,
        *,
        conectar: Callable[..., Any] | None = None,
        turno_continuo: bool = False,
    ) -> None:
        """Convierte fragmentos del LLM en PCM mientras ElevenLabs los genera."""
        if conectar is None:
            from websockets.asyncio.client import connect

            conectar = connect

        websocket: Any | None = None
        usar_nube = self.streaming_disponible
        error_conexion: BaseException | None = None
        indice = 0
        try:
            if usar_nube:
                try:
                    websocket = await conectar(
                        self._uri_streaming(),
                        max_size=None,
                        open_timeout=self.configuracion.timeout_segundos,
                    )
                    await websocket.send(json.dumps({
                        "voices": [self.configuracion.voice_id],
                        "xi_api_key": self.clave,
                        "voice_settings": {
                            "stability": self.configuracion.estabilidad,
                            "similarity_boost": self.configuracion.similitud,
                        },
                    }))
                except Exception as error:
                    usar_nube = False
                    error_conexion = error
                    await self._cerrar_websocket(websocket)
                    websocket = None

            if usar_nube and websocket is not None and turno_continuo:
                await self._producir_turno_continuo(
                    websocket,
                    cola_texto,
                    cola_audio,
                    ruta_base,
                )
                return

            while True:
                elemento = await cola_texto.get()
                if elemento is None:
                    break
                texto, confirmado, expresion = self._separar_fragmento(elemento)
                indice += 1

                if error_conexion is not None:
                    self._registrar(
                        texto,
                        "elevenlabs",
                        "error",
                        respaldo=False,
                        error=type(error_conexion).__name__,
                    )
                    await self._avisar_cambio_a_piper(
                        motivo_respaldo_voz(error_conexion),
                        ruta_base,
                        cola_audio,
                    )
                    error_conexion = None

                if usar_nube and websocket is not None:
                    recibio_audio = False
                    texto_expresivo = preparar_texto_expresivo(texto, expresion)
                    try:
                        await websocket.send(json.dumps({
                            "inputs": [{
                                "text": texto_expresivo,
                                "voice_id": self.configuracion.voice_id,
                                "new_turn": True,
                            }],
                            "flush": True,
                        }))
                        while True:
                            mensaje = json.loads(await websocket.recv())
                            if mensaje.get("error"):
                                raise ErrorElevenLabs(str(mensaje["error"]))
                            audio_codificado = mensaje.get("audio")
                            if audio_codificado:
                                datos = base64.b64decode(audio_codificado)
                                if not datos or len(datos) % 2:
                                    raise ErrorElevenLabs(
                                        "ElevenLabs devolvió PCM incremental inválido"
                                    )
                                recibio_audio = True
                                cola_audio.put(BloquePCM(datos))
                            if mensaje.get("is_final_audio_for_turn") is True:
                                break
                        cola_audio.put(BloquePCM(b"", confirmado, True))
                        self._proveedor_activo = "elevenlabs"
                        self._registrar(
                            texto,
                            "elevenlabs",
                            "ok",
                            respaldo=False,
                            caracteres_enviados=len(texto_expresivo),
                        )
                        continue
                    except Exception as error:
                        self._registrar(
                            texto,
                            "elevenlabs",
                            "error",
                            respaldo=False,
                            error=type(error).__name__,
                            caracteres_enviados=len(texto_expresivo),
                        )
                        usar_nube = False
                        await self._cerrar_websocket(websocket)
                        websocket = None
                        # Si el corte llegó a mitad de frase, Piper la repite
                        # completa para no dejar una respuesta truncada.
                        if recibio_audio:
                            cola_audio.put(BloquePCM(b"", None, True))
                        await self._avisar_cambio_a_piper(
                            motivo_respaldo_voz(error),
                            ruta_base,
                            cola_audio,
                        )

                if not usar_nube and error_conexion is None:
                    await self._avisar_cambio_a_piper(
                        "fallo",
                        ruta_base,
                        cola_audio,
                    )

                await self._producir_fragmento_piper(
                    texto,
                    confirmado,
                    indice,
                    ruta_base,
                    cola_audio,
                )
        finally:
            await self._cerrar_websocket(websocket)
            cola_audio.put(None)

    async def _producir_turno_continuo(
        self,
        websocket: Any,
        cola_texto: asyncio.Queue[Any],
        cola_audio: Any,
        ruta_base: Path,
    ) -> None:
        fragmentos: list[tuple[str, int | None, str | None, str]] = []
        recibio_audio = False

        async def enviar() -> None:
            direccion_anterior: str | None = None
            primero = True
            while True:
                elemento = await cola_texto.get()
                if elemento is None:
                    await websocket.send(json.dumps({"close_socket": True}))
                    return
                texto, confirmado, expresion = self._separar_fragmento(elemento)
                direccion = normalizar_direccion_voz(expresion)
                es_primero = primero
                if primero or direccion != direccion_anterior:
                    texto_enviado = preparar_texto_expresivo(texto, expresion)
                else:
                    texto_enviado = preparar_continuacion_voz(texto)
                primero = False
                direccion_anterior = direccion
                fragmentos.append((texto, confirmado, expresion, texto_enviado))
                mensaje = {
                    "inputs": [{
                        "text": texto_enviado,
                        "voice_id": self.configuracion.voice_id,
                        "new_turn": False,
                    }],
                }
                if es_primero:
                    mensaje["flush"] = True
                await websocket.send(json.dumps(mensaje))

        async def recibir() -> None:
            nonlocal recibio_audio
            while True:
                mensaje = json.loads(await websocket.recv())
                if mensaje.get("error"):
                    raise ErrorElevenLabs(str(mensaje["error"]))
                audio_codificado = mensaje.get("audio")
                if audio_codificado:
                    datos = base64.b64decode(audio_codificado)
                    if not datos or len(datos) % 2:
                        raise ErrorElevenLabs(
                            "ElevenLabs devolvió PCM incremental inválido"
                        )
                    recibio_audio = True
                    cola_audio.put(BloquePCM(datos))
                if mensaje.get("is_final") is True:
                    return

        tareas = [asyncio.create_task(enviar()), asyncio.create_task(recibir())]
        try:
            terminadas, pendientes = await asyncio.wait(
                tareas,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            error = next(
                (tarea.exception() for tarea in terminadas if tarea.exception()),
                None,
            )
            if error is not None:
                for tarea in pendientes:
                    tarea.cancel()
                await asyncio.gather(*pendientes, return_exceptions=True)
                raise error
            await asyncio.gather(*pendientes)
        except Exception as error:
            for tarea in tareas:
                if not tarea.done():
                    tarea.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)
            while True:
                elemento = await cola_texto.get()
                if elemento is None:
                    break
                texto, confirmado, expresion = self._separar_fragmento(elemento)
                fragmentos.append((texto, confirmado, expresion, texto))
            for indice, (texto, confirmado, _expresion, enviado) in enumerate(
                fragmentos,
                start=1,
            ):
                self._registrar(
                    texto,
                    "elevenlabs",
                    "error",
                    respaldo=False,
                    error=type(error).__name__,
                    caracteres_enviados=len(enviado),
                )
                if indice == 1:
                    await self._avisar_cambio_a_piper(
                        motivo_respaldo_voz(error),
                        ruta_base,
                        cola_audio,
                    )
                await self._producir_fragmento_piper(
                    texto,
                    confirmado,
                    indice,
                    ruta_base,
                    cola_audio,
                )
            if recibio_audio:
                cola_audio.put(BloquePCM(b"", None, True))
            return

        ultimo_confirmado = fragmentos[-1][1] if fragmentos else None
        cola_audio.put(BloquePCM(b"", ultimo_confirmado, True))
        self._proveedor_activo = "elevenlabs"
        for texto, _confirmado, _expresion, enviado in fragmentos:
            self._registrar(
                texto,
                "elevenlabs",
                "ok",
                respaldo=False,
                caracteres_enviados=len(enviado),
            )

    async def _avisar_cambio_a_piper(
        self,
        motivo: str,
        ruta_base: Path,
        cola_audio: Any,
    ) -> None:
        if self._proveedor_activo == "piper":
            return
        self._proveedor_activo = "piper"
        aviso = (
            AVISO_PIPER_CREDITOS
            if motivo == "creditos"
            else AVISO_PIPER_FALLO
        )
        await self._producir_fragmento_piper(
            aviso,
            None,
            0,
            ruta_base,
            cola_audio,
        )

    def _uri_streaming(self) -> str:
        base = self.configuracion.base_url.rstrip("/")
        if base.startswith("https://"):
            base = "wss://" + base[len("https://"):]
        return (
            f"{base}/v1/text-to-dialogue/stream-input"
            f"?model_id={quote(self.configuracion.modelo, safe='')}"
            f"&output_format={quote(self.configuracion.formato_streaming, safe='')}"
            "&language_code=es"
        )

    @staticmethod
    def _separar_fragmento(elemento: Any) -> tuple[str, int | None, str | None]:
        confirmado = None
        expresion = None
        if isinstance(elemento, tuple):
            if len(elemento) == 3:
                elemento, confirmado, expresion = elemento
            else:
                elemento, confirmado = elemento
        texto = str(elemento).strip()
        if not texto:
            raise ValueError("El fragmento de voz no puede estar vacío")
        return texto, confirmado, expresion

    async def _producir_fragmento_piper(
        self,
        texto: str,
        confirmado: int | None,
        indice: int,
        ruta_base: Path,
        cola_audio: Any,
    ) -> None:
        ruta = ruta_base.with_name(
            f"{ruta_base.stem}-respaldo-{indice:03d}{ruta_base.suffix}"
        )
        await asyncio.to_thread(
            self.sintetizador_local,
            texto,
            self.voz_piper,
            self.configuracion_piper,
            ruta,
        )
        datos = await asyncio.to_thread(self._leer_piper_16khz, ruta)
        cola_audio.put(BloquePCM(datos))
        cola_audio.put(BloquePCM(b"", confirmado, True))
        self._registrar(
            texto,
            "piper",
            "ok",
            respaldo=True,
            error=None if self.clave else "clave_ausente",
        )

    @staticmethod
    def _leer_piper_16khz(ruta: Path) -> bytes:
        import numpy as np
        from scipy.signal import resample_poly

        with wave.open(str(ruta), "rb") as archivo:
            if archivo.getnchannels() != 1 or archivo.getsampwidth() != 2:
                raise ValueError("Piper debe producir PCM mono de 16 bits")
            frecuencia = archivo.getframerate()
            muestras = np.frombuffer(
                archivo.readframes(archivo.getnframes()),
                dtype=np.int16,
            )
        if frecuencia != 16000:
            from math import gcd

            divisor = gcd(frecuencia, 16000)
            muestras = resample_poly(
                muestras.astype(np.float32),
                16000 // divisor,
                frecuencia // divisor,
            )
            muestras = np.clip(np.rint(muestras), -32768, 32767).astype(np.int16)
        return muestras.tobytes()

    @staticmethod
    async def _cerrar_websocket(websocket: Any | None) -> None:
        if websocket is None:
            return
        try:
            await websocket.send(json.dumps({"close_socket": True}))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass

    def __call__(
        self,
        texto: Any,
        _voz: Any,
        _configuracion: Any,
        salida: Path,
    ) -> InformeSintesis:
        direccion = getattr(texto, "expresion", None)
        texto_plano = getattr(texto, "texto", texto)
        if not isinstance(texto_plano, str):
            raise TypeError("El fragmento de voz debe contener texto")
        if self.clave:
            texto_expresivo = preparar_texto_expresivo(
                texto_plano,
                direccion,
            )
            try:
                informe = self.sintetizador_nube(
                    texto_expresivo,
                    self.clave,
                    self.configuracion,
                    salida,
                )
                self._registrar(
                    texto_plano,
                    "elevenlabs",
                    "ok",
                    respaldo=False,
                    caracteres_enviados=len(texto_expresivo),
                )
                return informe
            except Exception as error:
                self._registrar(
                    texto_plano,
                    "elevenlabs",
                    "error",
                    respaldo=False,
                    error=type(error).__name__,
                    caracteres_enviados=len(texto_expresivo),
                )

        if not self.configuracion.cambio_automatico:
            raise RuntimeError("La voz principal no está disponible")
        informe = self.sintetizador_local(
            texto_plano,
            self.voz_piper,
            self.configuracion_piper,
            salida,
        )
        self._registrar(
            texto_plano,
            "piper",
            "ok",
            respaldo=True,
            error=None if self.clave else "clave_ausente",
        )
        return informe

    def _registrar(self, *argumentos: Any, **opciones: Any) -> None:
        try:
            self.registrador(*argumentos, **opciones)
        except Exception:
            # Las métricas nunca deben dejar a ASTRO sin voz.
            return


def crear_sintetizador_voz(
    voz_piper: Any,
    configuracion_piper: Any,
    *,
    ruta_config: Path = RUTA_CONFIG,
    entorno: Mapping[str, str] = os.environ,
) -> SintetizadorConRespaldo:
    configuracion = cargar_configuracion_voz(ruta_config)
    clave = entorno.get(configuracion.clave_entorno, "").strip()
    return SintetizadorConRespaldo(
        configuracion,
        clave,
        voz_piper,
        configuracion_piper,
    )
