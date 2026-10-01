"""Validación automática de latencia, silencio e interrupción de la fase 36."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
from queue import Queue
from time import perf_counter
import wave

import numpy as np
from dotenv import load_dotenv
from scipy.signal import resample_poly

from core.expresion import INSTRUCCIONES_VOZ, ParserExpresionVoz
from voice.eco import CanceladorEco, FRECUENCIA_ECO_HZ, MUESTRAS_ECO
from voice.hablar import cargar_voz, crear_configuracion, sintetizar
from voice.interrupcion import DetectorInterrupcionEco
from voice.proveedor_voz import BloquePCM, crear_sintetizador_voz
from voice.realtime_prueba import SesionRealtimePrueba
from voice.streaming import SegmentadorTexto


RAIZ = Path(__file__).resolve().parents[1]
RUTA_AUDIOS = RAIZ / "data" / "audio" / "fase36-validacion"
SILENCIO_FINAL_SEGUNDOS = 0.5
PREBUFFER_DUPLEX_SEGUNDOS = 0.2
OBJETIVO_SEGUNDOS = 2.0

FRASES = {
    "callate": "Cállate.",
    "silencio": "Silencio.",
    "shhh": "Shhh, silencio.",
    "para": "Para de hablar.",
    "correccion": "No, mejor háblame de Júpiter.",
    "pregunta": "Dime un dato breve sobre Marte.",
}


@dataclass
class ResultadoCaso:
    nombre: str
    correcto: bool
    detalle: str


class ColaAudioMedida(Queue):
    def __init__(self, inicio: float) -> None:
        super().__init__()
        self.inicio = inicio
        self.primer_audio_segundos: float | None = None
        self.bloques: list[bytes] = []

    def put(self, item, *args, **kwargs) -> None:
        if isinstance(item, BloquePCM) and item.datos:
            if self.primer_audio_segundos is None:
                self.primer_audio_segundos = perf_counter() - self.inicio
            self.bloques.append(item.datos)
        super().put(item, *args, **kwargs)


def generar_audios() -> dict[str, Path]:
    RUTA_AUDIOS.mkdir(parents=True, exist_ok=True)
    voz = cargar_voz()
    configuracion = crear_configuracion("M")
    rutas: dict[str, Path] = {}
    for nombre, texto in FRASES.items():
        ruta = RUTA_AUDIOS / f"{nombre}.wav"
        sintetizar(texto, voz, configuracion, ruta)
        rutas[nombre] = ruta
    ruta_ast = RUTA_AUDIOS / "astro_largo.wav"
    sintetizar(
        "Marte es el cuarto planeta del sistema solar y conserva señales "
        "de agua antigua bajo una atmósfera muy delgada.",
        voz,
        configuracion,
        ruta_ast,
    )
    rutas["astro_largo"] = ruta_ast
    return rutas


def leer_wav_16khz(ruta: Path) -> np.ndarray:
    with wave.open(str(ruta), "rb") as archivo:
        frecuencia = archivo.getframerate()
        canales = archivo.getnchannels()
        ancho = archivo.getsampwidth()
        datos = archivo.readframes(archivo.getnframes())
    if canales != 1 or ancho != 2:
        raise ValueError(f"WAV incompatible: {ruta}")
    muestras = np.frombuffer(datos, dtype=np.int16)
    if frecuencia != FRECUENCIA_ECO_HZ:
        from math import gcd

        divisor = gcd(frecuencia, FRECUENCIA_ECO_HZ)
        muestras = resample_poly(
            muestras.astype(np.float32),
            FRECUENCIA_ECO_HZ // divisor,
            frecuencia // divisor,
        )
        muestras = np.clip(np.rint(muestras), -32768, 32767).astype(np.int16)
    return muestras


def validar_aec(rutas: dict[str, Path]) -> list[ResultadoCaso]:
    resultados: list[ResultadoCaso] = []
    referencia_base = leer_wav_16khz(rutas["astro_largo"])
    inicio_orden = FRECUENCIA_ECO_HZ
    retardo = int(FRECUENCIA_ECO_HZ * 0.04)

    def construir_microfono(orden: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
        longitud = max(
            len(referencia_base),
            inicio_orden + (len(orden) if orden is not None else 0) + 1600,
        )
        referencia = np.zeros(longitud, dtype=np.int16)
        referencia[:len(referencia_base)] = referencia_base
        mezcla = np.zeros(longitud, dtype=np.float64)
        mezcla[retardo:] += referencia[:-retardo].astype(np.float64) * 0.45
        if orden is not None:
            fin = inicio_orden + len(orden)
            mezcla[inicio_orden:fin] += orden.astype(np.float64) * 0.9
        microfono = np.clip(np.rint(mezcla), -32768, 32767).astype(np.int16)
        return referencia, microfono

    def detectar(orden: np.ndarray | None) -> float | None:
        referencia, microfono = construir_microfono(orden)
        cancelador = CanceladorEco(retardo_ms=40)
        detector = DetectorInterrupcionEco(cancelador)
        detector.preparar_fragmento()
        bloques = len(referencia) // MUESTRAS_ECO
        for indice in range(bloques):
            inicio = indice * MUESTRAS_ECO
            fin = inicio + MUESTRAS_ECO
            if detector.procesar(microfono[inicio:fin], referencia[inicio:fin]):
                return fin / FRECUENCIA_ECO_HZ
        return None

    falso = detectar(None)
    resultados.append(ResultadoCaso(
        "aec_sin_autocorte",
        falso is None,
        "sin detección" if falso is None else f"falso corte en {falso:.3f} s",
    ))
    for nombre in ("callate", "silencio", "shhh", "para", "correccion"):
        deteccion = detectar(leer_wav_16khz(rutas[nombre]))
        latencia = None if deteccion is None else deteccion - 1.0
        correcto = latencia is not None and 0 <= latencia < 0.5
        detalle = (
            "sin detección"
            if latencia is None
            else f"detección en {latencia:.3f} s"
        )
        resultados.append(ResultadoCaso(f"aec_{nombre}", correcto, detalle))
    return resultados


async def validar_control_realtime(
    rutas: dict[str, Path],
) -> list[ResultadoCaso]:
    instrucciones = (
        "Eres ASTRO. Responde en español de España con una sola frase breve. "
        "No uses herramientas salvo dormir_astro cuando el usuario ordene "
        "explícitamente callar o dejar de hablar.\n\n" + INSTRUCCIONES_VOZ
    )
    resultados: list[ResultadoCaso] = []
    async with SesionRealtimePrueba(instrucciones) as sesion:
        for nombre in ("callate", "silencio", "shhh", "para"):
            inicio = perf_counter()
            resultado = await sesion.responder(rutas[nombre], lambda _texto: None)
            duracion = perf_counter() - inicio
            resultados.append(ResultadoCaso(
                f"realtime_{nombre}",
                resultado.ordenar_silencio,
                f"control={resultado.ordenar_silencio} en {duracion:.3f} s",
            ))
        for nombre in ("correccion", "pregunta"):
            resultado = await sesion.responder(rutas[nombre], lambda _texto: None)
            correcto = not resultado.ordenar_silencio and bool(resultado.texto)
            resultados.append(ResultadoCaso(
                f"realtime_{nombre}",
                correcto,
                "respuesta normal" if correcto else "clasificación incorrecta",
            ))
    return resultados


async def medir_latencia(
    rutas: dict[str, Path],
) -> list[ResultadoCaso]:
    voz_piper = await asyncio.to_thread(cargar_voz)
    configuracion_piper = crear_configuracion("M")
    sintetizador = crear_sintetizador_voz(voz_piper, configuracion_piper)
    instrucciones = (
        "Eres ASTRO. Responde en español de España con una sola frase de "
        "máximo doce palabras.\n\n" + INSTRUCCIONES_VOZ
    )
    resultados: list[ResultadoCaso] = []
    async with SesionRealtimePrueba(instrucciones) as sesion:
        for indice in range(1, 11):
            inicio = perf_counter()
            cola_texto: asyncio.Queue = asyncio.Queue()
            cola_audio = ColaAudioMedida(inicio)
            productor = asyncio.create_task(sintetizador.producir_streaming(
                cola_texto,
                cola_audio,
                RUTA_AUDIOS / f"latencia_{indice}.wav",
                turno_continuo=True,
            ))
            segmentador = SegmentadorTexto()
            expresion: str | None = None
            primer_texto: float | None = None

            def publicar(fragmento: str) -> None:
                nonlocal primer_texto
                if primer_texto is None:
                    primer_texto = perf_counter() - inicio
                for parte in segmentador.agregar(fragmento):
                    cola_texto.put_nowait((parte, None, expresion))

            def cambiar(direccion: str) -> None:
                nonlocal expresion
                expresion = direccion

            parser = ParserExpresionVoz(publicar, cambiar)
            respuesta = await sesion.responder(rutas["pregunta"], parser.agregar)
            parser.finalizar()
            if respuesta.ordenar_silencio:
                await cola_texto.put(None)
                await productor
                resultados.append(ResultadoCaso(
                    f"latencia_{indice}", False, "clasificada como silencio",
                ))
                continue
            for parte in segmentador.finalizar():
                await cola_texto.put((parte, None, expresion))
            await cola_texto.put(None)
            await productor
            if cola_audio.primer_audio_segundos is None:
                resultados.append(ResultadoCaso(
                    f"latencia_{indice}", False, "ElevenLabs no produjo audio",
                ))
                continue
            estimada = (
                cola_audio.primer_audio_segundos
                + SILENCIO_FINAL_SEGUNDOS
                + PREBUFFER_DUPLEX_SEGUNDOS
            )
            duplicados = sum(
                anterior == actual
                for anterior, actual in zip(
                    cola_audio.bloques,
                    cola_audio.bloques[1:],
                )
            )
            correcto = estimada < OBJETIVO_SEGUNDOS and duplicados == 0
            resultados.append(ResultadoCaso(
                f"latencia_{indice}",
                correcto,
                f"{estimada:.3f} s estimados; "
                f"primer texto={primer_texto:.3f} s; "
                f"primer PCM={cola_audio.primer_audio_segundos:.3f} s; "
                f"bloques duplicados={duplicados}",
            ))
    return resultados


def imprimir(resultados: list[ResultadoCaso]) -> bool:
    correcto = True
    for resultado in resultados:
        marca = "PASS" if resultado.correcto else "FAIL"
        print(f"[{marca}] {resultado.nombre}: {resultado.detalle}")
        correcto &= resultado.correcto
    print(f"RESULTADO: {'PASS' if correcto else 'FAIL'}")
    return correcto


async def ejecutar() -> bool:
    load_dotenv(RAIZ / ".env")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("Falta OPENAI_API_KEY")
    if not os.getenv("ELEVENLABS_API_KEY", "").strip():
        raise RuntimeError("Falta ELEVENLABS_API_KEY")
    rutas = await asyncio.to_thread(generar_audios)
    resultados = await asyncio.to_thread(validar_aec, rutas)
    resultados.extend(await validar_control_realtime(rutas))
    resultados.extend(await medir_latencia(rutas))
    return imprimir(resultados)


def main() -> int:
    return 0 if asyncio.run(ejecutar()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
