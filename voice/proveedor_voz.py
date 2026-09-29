from __future__ import annotations

import json
import os
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
    velocidad: float


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
        velocidad=float(nube.get("velocidad", 0)),
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
    if configuracion.modelo != "eleven_flash_v2_5":
        raise ValueError("La fase 35 requiere eleven_flash_v2_5")
    if configuracion.formato != f"pcm_{configuracion.frecuencia_hz}":
        raise ValueError("El formato PCM no coincide con su frecuencia")
    if configuracion.frecuencia_hz not in {16000, 22050, 24000}:
        raise ValueError("Frecuencia PCM no admitida")
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
    if not 0.7 <= configuracion.velocidad <= 1.2:
        raise ValueError("velocidad debe estar entre 0.7 y 1.2")


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
                "style": 0.0,
                "use_speaker_boost": True,
                "speed": configuracion.velocidad,
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
    ruta: Path = RUTA_USO,
) -> None:
    registro = {
        "fecha": datetime.now(timezone.utc).isoformat(),
        "proveedor": proveedor,
        "caracteres": len(texto),
        "resultado": resultado,
        "respaldo": respaldo,
    }
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

    @property
    def principal_disponible(self) -> bool:
        return bool(self.clave)

    def __call__(
        self,
        texto: str,
        _voz: Any,
        _configuracion: Any,
        salida: Path,
    ) -> InformeSintesis:
        if self.clave:
            try:
                informe = self.sintetizador_nube(
                    texto,
                    self.clave,
                    self.configuracion,
                    salida,
                )
                self._registrar(
                    texto,
                    "elevenlabs",
                    "ok",
                    respaldo=False,
                )
                return informe
            except Exception as error:
                self._registrar(
                    texto,
                    "elevenlabs",
                    "error",
                    respaldo=False,
                    error=type(error).__name__,
                )

        if not self.configuracion.cambio_automatico:
            raise RuntimeError("La voz principal no está disponible")
        informe = self.sintetizador_local(
            texto,
            self.voz_piper,
            self.configuracion_piper,
            salida,
        )
        self._registrar(
            texto,
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
