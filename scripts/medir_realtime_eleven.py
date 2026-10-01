"""Prueba reversible: audio grabado -> OpenAI Realtime -> ElevenLabs."""

import asyncio
import os
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from core.expresion import INSTRUCCIONES_VOZ
from voice.hablar import cargar_voz, crear_configuracion
from voice.proveedor_voz import crear_sintetizador_voz
from voice.realtime_prueba import SesionRealtimePrueba
from voice.streaming import SegmentadorTexto, reproducir_cola_streaming


RAIZ = Path(__file__).resolve().parents[1]
RUTA_AUDIO = RAIZ / "data" / "audio" / "pregunta-voz.wav"
async def medir() -> None:
    load_dotenv(RAIZ / ".env")
    clave = os.getenv("OPENAI_API_KEY", "").strip()
    if not clave:
        raise RuntimeError("Falta OPENAI_API_KEY")
    voz_piper = await asyncio.to_thread(cargar_voz)
    configuracion_piper = crear_configuracion()
    sintetizador = crear_sintetizador_voz(voz_piper, configuracion_piper)
    cola_texto = asyncio.Queue()
    instrucciones = (
        "Eres ASTRO, el asistente personal de Jhony. Responde en español de "
        "España, de forma natural, directa y breve. Esta prueba no permite "
        "herramientas ni acciones.\n\n" + INSTRUCCIONES_VOZ
    )
    async with SesionRealtimePrueba(instrucciones) as sesion:
        inicio = perf_counter()
        tarea_voz = asyncio.create_task(reproducir_cola_streaming(
            cola_texto,
            voz_piper,
            configuracion_piper,
            None,
            RAIZ / "data" / "audio" / "realtime-prueba.wav",
            inicio,
            sintetizador=sintetizador,
        ))
        segmentador = SegmentadorTexto()
        texto_completo = ""
        primer_texto = None

        def recibir(fragmento: str) -> None:
            nonlocal primer_texto, texto_completo
            if primer_texto is None:
                primer_texto = perf_counter() - inicio
            texto_completo += fragmento
            print(fragmento, end="", flush=True)
            for parte in segmentador.agregar(fragmento):
                cola_texto.put_nowait((parte, len(texto_completo), None))

        await sesion.responder(RUTA_AUDIO, recibir)

        for parte in segmentador.finalizar():
            await cola_texto.put((parte, len(texto_completo), None))
        await cola_texto.put(None)
        resultado_voz = await tarea_voz

    print()
    if primer_texto is None:
        raise RuntimeError("Realtime no produjo texto")
    print(f"Primer texto Realtime: {primer_texto:.3f} s")
    print(f"Primera voz ElevenLabs: {resultado_voz.latencia_primera_voz:.3f} s")
    print("Estimación con silencio final local: "
          f"{resultado_voz.latencia_primera_voz + 0.5:.3f} s")


def main() -> int:
    asyncio.run(medir())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
