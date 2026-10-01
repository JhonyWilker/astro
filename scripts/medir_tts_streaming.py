"""Mide el primer bloque y la descarga completa de un modelo ElevenLabs."""

from argparse import ArgumentParser
import json
import os
import wave
from pathlib import Path
from time import perf_counter
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from voice.proveedor_voz import (
    cargar_configuracion_voz,
    preparar_texto_expresivo,
)


RAIZ = Path(__file__).resolve().parents[1]
TAMANO_PRIMER_BLOQUE = 4096


def main() -> int:
    argumentos = ArgumentParser()
    argumentos.add_argument("--modelo")
    argumentos.add_argument("--salida", type=Path)
    opciones = argumentos.parse_args()
    load_dotenv(RAIZ / ".env")
    configuracion = cargar_configuracion_voz()
    modelo = opciones.modelo or configuracion.modelo
    clave = os.environ.get(configuracion.clave_entorno, "").strip()
    if not clave:
        raise RuntimeError("Falta la clave de ElevenLabs")

    texto = preparar_texto_expresivo(
        "Entendido, Jhony.",
        "calm, warm, attentive",
    )
    cuerpo = json.dumps({
        "text": texto,
        "model_id": modelo,
        "language_code": "es",
        "voice_settings": {
            "stability": configuracion.estabilidad,
            "similarity_boost": configuracion.similitud,
        },
    }).encode("utf-8")
    url = (
        f"{configuracion.base_url.rstrip('/')}/v1/text-to-speech/"
        f"{quote(configuracion.voice_id, safe='')}/stream"
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

    inicio = perf_counter()
    respuesta = urlopen(
        peticion,
        timeout=configuracion.timeout_segundos,
    )
    conectado = perf_counter() - inicio
    try:
        primer_bloque = respuesta.read(TAMANO_PRIMER_BLOQUE)
        primer_audio = perf_counter() - inicio
        bloques = [primer_bloque]
        while bloque := respuesta.read(65536):
            bloques.append(bloque)
        completo = perf_counter() - inicio
    finally:
        respuesta.close()

    audio = b"".join(bloques)
    if opciones.salida is not None:
        opciones.salida.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(opciones.salida), "wb") as archivo:
            archivo.setnchannels(1)
            archivo.setsampwidth(2)
            archivo.setframerate(configuracion.frecuencia_hz)
            archivo.writeframes(audio)

    print(f"Modelo: {modelo}")
    print(f"HTTP conectado: {conectado:.3f} s")
    print(f"Primeros {len(primer_bloque)} bytes: {primer_audio:.3f} s")
    print(f"Audio completo: {completo:.3f} s")
    print(f"PCM total: {len(audio)} bytes")
    if opciones.salida is not None:
        print(f"WAV: {opciones.salida.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
