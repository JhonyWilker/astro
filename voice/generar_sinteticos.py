"""Genera con Piper los audios sintéticos para entrenar «Astro».

Para cada voz, velocidad y variación de entonación crea clips de 16 kHz:
- positivas: alguien llamando a Astro (el clip termina en «Astro»);
- negativas: frases habladas normales y palabras parecidas.
"""

import json
import random
import re
import wave
from argparse import ArgumentParser
from math import gcd
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import resample_poly

from voice.activacion import FRECUENCIA_HZ
from voice.corpus_activacion import (
    CONTINUACIONES,
    FRASES_CON_ASTRO,
    FRASES_NEGATIVAS,
    PALABRAS_CON_ASTRO,
    PALABRAS_PARECIDAS,
    PREFIJOS_POSITIVOS,
)
from voice.vad_silero import RAIZ_PROYECTO


CARPETA_VOCES = RAIZ_PROYECTO / "data" / "models" / "piper"
CARPETA_SINTETICOS = RAIZ_PROYECTO / "data" / "wakeword" / "sinteticos"
VELOCIDADES_POSITIVAS = (0.8, 0.9, 1.0, 1.1, 1.25)
VELOCIDADES_NEGATIVAS = (0.9, 1.1)


def guardar_wav16(ruta: Path, muestras: np.ndarray) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(FRECUENCIA_HZ)
        archivo.writeframes(muestras.astype(np.int16).tobytes())


def a_16khz(datos: bytes, frecuencia: int) -> np.ndarray:
    audio = np.frombuffer(datos, dtype=np.int16).astype(np.float32)
    if frecuencia != FRECUENCIA_HZ:
        divisor = gcd(frecuencia, FRECUENCIA_HZ)
        audio = resample_poly(
            audio,
            FRECUENCIA_HZ // divisor,
            frecuencia // divisor,
        )
    return np.clip(audio, -32768, 32767).astype(np.int16)


def sintetizar_16khz(
    voz: Any,
    texto: str,
    hablante: int | None,
    velocidad: float,
    aleatorio: random.Random,
) -> np.ndarray:
    from piper import SynthesisConfig

    configuracion = SynthesisConfig(
        speaker_id=hablante,
        length_scale=velocidad,
        noise_scale=aleatorio.uniform(0.5, 0.9),
        noise_w_scale=aleatorio.uniform(0.6, 1.0),
    )
    fragmentos = [
        bloque.audio_int16_bytes
        for bloque in voz.synthesize(texto, syn_config=configuracion)
    ]
    return a_16khz(b"".join(fragmentos), voz.config.sample_rate)


def unir_con_continuacion(
    voz: Any,
    hablante: int | None,
    velocidad: float,
    continuacion: str,
    aleatorio: random.Random,
) -> tuple[np.ndarray | None, float]:
    """«Astro» seguido de una orden. Devuelve el clip y el segundo en que acaba «Astro»."""
    from voice.entrenar_activacion import fin_de_habla

    palabra = sintetizar_16khz(voz, "Astro,", hablante, velocidad, aleatorio)
    fin = fin_de_habla(palabra, _vad_compartido())
    if fin is None:
        return None, 0.0
    resto = sintetizar_16khz(voz, continuacion, hablante, velocidad, aleatorio)
    pausa = np.zeros(int(aleatorio.uniform(0.03, 0.3) * FRECUENCIA_HZ), dtype=np.int16)
    recorte = palabra[: int((fin + 0.03) * FRECUENCIA_HZ)]
    return np.concatenate((recorte, pausa, resto)), fin


_VAD: list = []


def _vad_compartido():
    from voice.vad_silero import VadSilero

    if not _VAD:
        _VAD.append(VadSilero())
    return _VAD[0]


def listar_voces(carpeta: Path = CARPETA_VOCES) -> list[tuple[str, Path, int | None]]:
    """Devuelve (nombre, ruta, hablante) por cada voz o hablante disponible."""
    import json

    resultado: list[tuple[str, Path, int | None]] = []
    for ruta in sorted(carpeta.glob("es_*.onnx")):
        configuracion = json.loads(
            Path(f"{ruta}.json").read_text(encoding="utf-8")
        )
        hablantes = int(configuracion.get("num_speakers", 1))
        if hablantes <= 1:
            resultado.append((ruta.stem, ruta, None))
        else:
            resultado.extend(
                (f"{ruta.stem}-h{indice}", ruta, indice)
                for indice in range(hablantes)
            )
    return resultado


VOCES_EXTRANJERAS = {
    "en_US-libritts_r-medium": 200,
    "de_DE-mls-medium": 120,
    "en_US-l2arctic-medium": 24,
}
PREFIJO_EXTRANJERAS = tuple(VOCES_EXTRANJERAS)


def es_validacion_sintetica(nombre_archivo: str) -> bool:
    """Voz o hablantes reservados para validar, nunca para entrenar."""
    if "es_AR-daniela" in nombre_archivo:
        return True
    coincidencia = re.match(r"(?:en_US|de_DE)-[\w-]+?-h(\d+)_", nombre_archivo)
    return coincidencia is not None and int(coincidencia.group(1)) % 7 == 0


def listar_voces_extranjeras(
    carpeta: Path = CARPETA_VOCES,
    semilla: int = 29,
) -> list[tuple[str, Path, int | None]]:
    """Una muestra de hablantes de voces multihablante de otros idiomas."""
    aleatorio = random.Random(semilla)
    resultado: list[tuple[str, Path, int | None]] = []
    for nombre, cantidad in VOCES_EXTRANJERAS.items():
        ruta = carpeta / f"{nombre}.onnx"
        if not ruta.is_file():
            continue
        configuracion = json.loads(Path(f"{ruta}.json").read_text(encoding="utf-8"))
        total = int(configuracion.get("num_speakers", 1))
        elegidos = sorted(aleatorio.sample(range(total), min(cantidad, total)))
        resultado.extend((f"{nombre}-h{indice}", ruta, indice) for indice in elegidos)
    return resultado


def generar_confusas(
    carpeta: Path = CARPETA_SINTETICOS,
    voces: list[tuple[str, Path, int | None]] | None = None,
    semilla: int = 29,
) -> int:
    """Palabras y frases con «astro» dentro (astronauta, castro, rastro...)."""
    from piper import PiperVoice

    aleatorio = random.Random(semilla)
    voces = voces if voces is not None else listar_voces()
    cargadas: dict[Path, Any] = {}
    total = 0
    for nombre, ruta_voz, hablante in voces:
        if ruta_voz not in cargadas:
            cargadas[ruta_voz] = PiperVoice.load(
                ruta_voz, config_path=Path(f"{ruta_voz}.json")
            )
        voz = cargadas[ruta_voz]
        indice = 0
        trabajos = [
            (texto, velocidad)
            for texto in PALABRAS_CON_ASTRO
            for velocidad in (0.9, 1.0, 1.15)
        ] + [
            (texto, velocidad)
            for texto in FRASES_CON_ASTRO
            for velocidad in (0.95, 1.1)
        ]
        for texto, velocidad in trabajos:
            indice += 1
            audio = sintetizar_16khz(voz, texto, hablante, velocidad, aleatorio)
            guardar_wav16(carpeta / "negativas_confusas" / f"{nombre}_{indice:04d}.wav", audio)
            total += 1
        print(f"{nombre}: {total} acumuladas", flush=True)
    return total


def generar_extranjeras(
    carpeta: Path = CARPETA_SINTETICOS,
    voces: list[tuple[str, Path, int | None]] | None = None,
    semilla: int = 29,
) -> dict[str, int]:
    """Pocas muestras por hablante, pero de cientos de hablantes distintos."""
    from piper import PiperVoice

    aleatorio = random.Random(semilla)
    contadores = {"positivas": 0, "positivas_continuas": 0, "negativas": 0}
    voces = voces if voces is not None else listar_voces_extranjeras()
    cargadas: dict[Path, Any] = {}

    for nombre, ruta_voz, hablante in voces:
        if ruta_voz not in cargadas:
            cargadas[ruta_voz] = PiperVoice.load(
                ruta_voz, config_path=Path(f"{ruta_voz}.json")
            )
        voz = cargadas[ruta_voz]
        indice = 0
        for texto in aleatorio.sample(PREFIJOS_POSITIVOS, 4):
            indice += 1
            velocidad = aleatorio.choice(VELOCIDADES_POSITIVAS)
            audio = sintetizar_16khz(voz, texto, hablante, velocidad, aleatorio)
            guardar_wav16(carpeta / "positivas" / f"{nombre}_{indice:04d}.wav", audio)
            contadores["positivas"] += 1

        clip, fin = unir_con_continuacion(
            voz, hablante, aleatorio.choice((1.0, 1.15)),
            aleatorio.choice(CONTINUACIONES), aleatorio,
        )
        if clip is not None:
            guardar_wav16(
                carpeta / "positivas_continuas" / f"{nombre}_0001_fin{int(fin * 1000)}ms.wav",
                clip,
            )
            contadores["positivas_continuas"] += 1

        textos = (
            *aleatorio.sample(FRASES_NEGATIVAS, 6),
            *aleatorio.sample(PALABRAS_PARECIDAS, 4),
        )
        for indice, texto in enumerate(textos, start=1):
            velocidad = aleatorio.choice(VELOCIDADES_NEGATIVAS)
            audio = sintetizar_16khz(voz, texto, hablante, velocidad, aleatorio)
            guardar_wav16(carpeta / "negativas" / f"{nombre}_{indice:04d}.wav", audio)
            contadores["negativas"] += 1
    print(f"{contadores}", flush=True)
    return contadores


def generar(
    carpeta: Path = CARPETA_SINTETICOS,
    voces: list[tuple[str, Path, int | None]] | None = None,
    semilla: int = 29,
    solo_continuas: bool = False,
) -> dict[str, int]:
    from piper import PiperVoice

    aleatorio = random.Random(semilla)
    contadores = {"positivas": 0, "positivas_continuas": 0, "negativas": 0}
    voces = voces if voces is not None else listar_voces()
    cargadas: dict[Path, Any] = {}

    def guardar(tipo: str, nombre: str, indice: int, audio: np.ndarray) -> None:
        ruta = carpeta / tipo / f"{nombre}_{indice:04d}.wav"
        guardar_wav16(ruta, audio)
        contadores[tipo] += 1

    for nombre, ruta_voz, hablante in voces:
        if ruta_voz not in cargadas:
            cargadas[ruta_voz] = PiperVoice.load(
                ruta_voz,
                config_path=Path(f"{ruta_voz}.json"),
            )
        voz = cargadas[ruta_voz]
        indice = 0

        for texto in () if solo_continuas else PREFIJOS_POSITIVOS:
            for velocidad in VELOCIDADES_POSITIVAS:
                for _ in range(2):
                    indice += 1
                    guardar(
                        "positivas",
                        nombre,
                        indice,
                        sintetizar_16khz(voz, texto, hablante, velocidad, aleatorio),
                    )

        indice = 0
        for continuacion in CONTINUACIONES:
            for velocidad in (1.0, 1.15):
                indice += 1
                clip, fin = unir_con_continuacion(
                    voz, hablante, velocidad, continuacion, aleatorio
                )
                if clip is None:
                    continue
                ruta = (
                    carpeta
                    / "positivas_continuas"
                    / f"{nombre}_{indice:04d}_fin{int(fin * 1000)}ms.wav"
                )
                guardar_wav16(ruta, clip)
                contadores["positivas_continuas"] += 1

        indice = 0
        for texto in () if solo_continuas else (*FRASES_NEGATIVAS, *PALABRAS_PARECIDAS):
            for velocidad in VELOCIDADES_NEGATIVAS:
                indice += 1
                guardar(
                    "negativas",
                    nombre,
                    indice,
                    sintetizar_16khz(voz, texto, hablante, velocidad, aleatorio),
                )
        print(
            f"{nombre}: {contadores['positivas']} positivas y "
            f"{contadores['negativas']} negativas acumuladas",
            flush=True,
        )
    return contadores


def main() -> int:
    argumentos = ArgumentParser(description=__doc__)
    argumentos.add_argument("--carpeta", type=Path, default=CARPETA_SINTETICOS)
    argumentos.add_argument(
        "--voces",
        nargs="+",
        help="Solo las voces cuyo nombre contenga alguno de estos textos.",
    )
    argumentos.add_argument("--solo-continuas", action="store_true")
    argumentos.add_argument(
        "--confusas",
        action="store_true",
        help="Genera palabras y frases con «astro» dentro (astronauta, castro...).",
    )
    argumentos.add_argument(
        "--extranjeras",
        action="store_true",
        help="Genera pocas muestras de cientos de hablantes de otros idiomas.",
    )
    opciones = argumentos.parse_args()
    if opciones.extranjeras:
        voces_extranjeras = listar_voces_extranjeras()
        if opciones.voces:
            voces_extranjeras = [
                voz for voz in voces_extranjeras
                if any(filtro in voz[0] for filtro in opciones.voces)
            ]
        generar_extranjeras(opciones.carpeta, voces_extranjeras)
        return 0
    voces = listar_voces()
    if opciones.confusas:
        if opciones.voces:
            voces = [v for v in voces if any(f in v[0] for f in opciones.voces)]
        generar_confusas(opciones.carpeta, voces)
        return 0
    if opciones.voces:
        voces = [
            voz
            for voz in voces
            if any(filtro in voz[0] for filtro in opciones.voces)
        ]
    contadores = generar(
        opciones.carpeta, voces, solo_continuas=opciones.solo_continuas
    )
    print(f"Listo: {contadores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
