"""Mide el detector de «Astro» completo con audio que no se usó para entrenar.

Pasa por el mismo camino que en directo (filtro de voz, bloques seguidos y
descanso) tus grabaciones reservadas y varios minutos de habla ajena.
"""

import json
from argparse import ArgumentParser
from pathlib import Path

import numpy as np

from voice.activacion import (
    ConfiguracionActivacion,
    DetectorActivacion,
    FRECUENCIA_HZ,
    MUESTRAS_ACTIVACION,
)
from voice.entrenar_activacion import (
    CARPETA_MUESTRAS,
    RUTA_AJUSTES_ASTRO,
    RUTA_FLUJO_CONFUSAS,
    RUTA_MODELO_ASTRO,
    RUTA_RESERVADAS,
    cargar_wav16,
    construir_flujo_real,
)


def activaciones_en(detector: DetectorActivacion, señal: np.ndarray) -> list[float]:
    """Segundos en los que el detector se activa al recibir la señal completa."""
    detector.reiniciar()
    instantes = []
    for inicio in range(0, len(señal) - MUESTRAS_ACTIVACION + 1, MUESTRAS_ACTIVACION):
        if detector.alimentar(señal[inicio:inicio + MUESTRAS_ACTIVACION]) is not None:
            instantes.append((inicio + MUESTRAS_ACTIVACION) / FRECUENCIA_HZ)
    return instantes


def rodear_de_silencio(clip: np.ndarray, aleatorio: np.random.Generator) -> np.ndarray:
    ruido = lambda segundos: aleatorio.normal(0, 3, int(segundos * FRECUENCIA_HZ)).astype(np.int16)
    return np.concatenate((ruido(1.6), clip, ruido(1.2)))


def evaluar_positivas(detector, rutas: list[Path], semilla: int = 0) -> tuple[int, int]:
    aleatorio = np.random.default_rng(semilla)
    detectadas = 0
    for ruta in rutas:
        señal = rodear_de_silencio(cargar_wav16(ruta), aleatorio)
        detectadas += bool(activaciones_en(detector, señal))
    return detectadas, len(rutas)


def evaluar_falsas(detector, flujo: np.ndarray) -> tuple[int, float]:
    horas = len(flujo) / FRECUENCIA_HZ / 3600
    return len(activaciones_en(detector, flujo)), horas


def main() -> int:
    argumentos = ArgumentParser(description=__doc__)
    argumentos.add_argument("--modelo", type=Path, default=RUTA_MODELO_ASTRO)
    argumentos.add_argument("--umbral", type=float)
    argumentos.add_argument("--consecutivos", type=int)
    argumentos.add_argument("--todas", action="store_true", help="Incluye las grabaciones usadas para entrenar.")
    opciones = argumentos.parse_args()

    ajustes = {}
    if RUTA_AJUSTES_ASTRO.is_file():
        ajustes = json.loads(RUTA_AJUSTES_ASTRO.read_text(encoding="utf-8"))
    umbral = opciones.umbral or ajustes.get("umbral", 0.5)
    consecutivos = opciones.consecutivos or ajustes.get("bloques_consecutivos", 1)
    detector = DetectorActivacion(
        ConfiguracionActivacion(
            ruta_modelo=opciones.modelo,
            umbral=umbral,
            bloques_consecutivos=consecutivos,
        )
    )

    if opciones.todas:
        rutas = sorted((CARPETA_MUESTRAS / "positivas").rglob("*.wav"))
        etiqueta = "todas las grabaciones (incluye las de entrenamiento)"
    else:
        reservadas = json.loads(RUTA_RESERVADAS.read_text(encoding="utf-8"))
        rutas = [CARPETA_MUESTRAS / nombre for nombre in reservadas]
        etiqueta = "grabaciones reservadas"
    detectadas, total = evaluar_positivas(detector, rutas)
    print(f"Umbral {umbral} · {consecutivos} bloque(s) seguido(s)")
    print(f"Tus {etiqueta}: {detectadas}/{total} detectadas")

    if RUTA_FLUJO_CONFUSAS.is_file():
        confusas = np.load(RUTA_FLUJO_CONFUSAS)
        activadas = activaciones_en(detector, confusas)
        print(
            f"Palabras parecidas reservadas (astronauta, castro...): "
            f"{len(activadas)} activación(es) en {len(confusas) / FRECUENCIA_HZ:.0f} s de audio"
        )

    flujo = construir_flujo_real()
    falsas, horas = evaluar_falsas(detector, flujo)
    print(
        f"Habla ajena: {falsas} activación(es) en {horas * 60:.1f} min "
        f"({falsas / horas:.1f} por hora de habla continua)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
