"""Mide el primer audio de Eleven v4 mediante Text to Dialogue."""

import asyncio
import base64
import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from websockets.asyncio.client import connect

from voice.proveedor_voz import (
    cargar_configuracion_voz,
    preparar_texto_expresivo,
)


RAIZ = Path(__file__).resolve().parents[1]


async def medir() -> None:
    load_dotenv(RAIZ / ".env")
    configuracion = cargar_configuracion_voz()
    clave = os.environ.get(configuracion.clave_entorno, "").strip()
    if not clave:
        raise RuntimeError("Falta la clave de ElevenLabs")

    uri = (
        "wss://api.elevenlabs.io/v1/text-to-dialogue/stream-input"
        f"?model_id={configuracion.modelo}"
        f"&output_format={configuracion.formato}"
        "&language_code=es"
    )
    inicio = perf_counter()
    async with connect(uri, max_size=None) as websocket:
        conectado = perf_counter() - inicio
        await websocket.send(json.dumps({
            "voices": [configuracion.voice_id],
            "xi_api_key": clave,
            "voice_settings": {
                "stability": configuracion.estabilidad,
                "similarity_boost": configuracion.similitud,
            },
        }))
        texto = preparar_texto_expresivo(
            "Entendido, Jhony. Estoy listo para ayudarte.",
            "calm, warm, attentive",
        )
        inicio_texto = perf_counter()
        await websocket.send(json.dumps({
            "inputs": [{
                "text": texto,
                "voice_id": configuracion.voice_id,
                "new_turn": True,
            }],
            "flush": True,
        }))

        primer_audio: float | None = None
        total = 0
        while True:
            mensaje = json.loads(await websocket.recv())
            if audio := mensaje.get("audio"):
                if primer_audio is None:
                    primer_audio = perf_counter() - inicio_texto
                total += len(base64.b64decode(audio))
            if mensaje.get("is_final_audio_for_turn") is True:
                break
            if mensaje.get("error"):
                raise RuntimeError(str(mensaje["error"]))

        completo = perf_counter() - inicio_texto
        await websocket.send(json.dumps({"close_socket": True}))

    if primer_audio is None:
        raise RuntimeError("ElevenLabs no devolvió audio")
    print(f"WebSocket conectado: {conectado:.3f} s")
    print(f"Primer audio tras enviar texto: {primer_audio:.3f} s")
    print(f"Turno completo: {completo:.3f} s")
    print(f"PCM total: {total} bytes")


def main() -> int:
    asyncio.run(medir())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
