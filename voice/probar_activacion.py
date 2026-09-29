from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np

from clients.grabar_audio import (
    CANALES,
    FORMATO_MUESTRA,
    cargar_sounddevice,
)
from voice.activacion import (
    DetectorActivacion,
    FRECUENCIA_HZ,
    MUESTRAS_ACTIVACION,
    configuracion_predeterminada,
    registrar_activacion,
)


def crear_argumentos() -> ArgumentParser:
    argumentos = ArgumentParser(
        description=(
            "Escucha el micrófono y cuenta las activaciones, sin conectar "
            "con ASTRO. Sirve para medir falsos positivos."
        ),
    )
    argumentos.add_argument("--modelo", type=Path)
    argumentos.add_argument("--umbral", type=float)
    argumentos.add_argument("--consecutivos", type=int)
    argumentos.add_argument("--microfono", type=int)
    argumentos.add_argument(
        "--minutos",
        type=float,
        default=0,
        help="Duración de la prueba. 0 significa hasta pulsar Ctrl+C.",
    )
    return argumentos


def escuchar(opciones) -> tuple[int, float, float]:
    configuracion = configuracion_predeterminada(opciones.modelo)
    cambios = {
        campo: valor
        for campo, valor in (
            ("umbral", opciones.umbral),
            ("bloques_consecutivos", opciones.consecutivos),
        )
        if valor is not None
    }
    detector = DetectorActivacion(replace(configuracion, **cambios))
    audio = cargar_sounddevice()
    limite = opciones.minutos * 60 if opciones.minutos else None
    activaciones = 0
    desbordamientos = 0
    inicio = perf_counter()

    print("Escuchando. Pulsa Ctrl+C para terminar.")
    try:
        with audio.RawInputStream(
            samplerate=FRECUENCIA_HZ,
            device=opciones.microfono,
            channels=CANALES,
            dtype=FORMATO_MUESTRA,
        ) as flujo:
            while limite is None or perf_counter() - inicio < limite:
                datos, desbordado = flujo.read(MUESTRAS_ACTIVACION)
                desbordamientos += int(desbordado)
                activacion = detector.alimentar(
                    np.frombuffer(bytes(datos), dtype=np.int16)
                )
                if activacion is None:
                    continue
                activaciones += 1
                registrar_activacion(activacion)
                minutos = (perf_counter() - inicio) / 60
                print(
                    f"[{minutos:6.1f} min] activación {activaciones} · "
                    f"puntuación {activacion.puntuacion:.2f}",
                    flush=True,
                )
    except KeyboardInterrupt:
        pass

    horas = (perf_counter() - inicio) / 3600
    if desbordamientos:
        print(f"Aviso: hubo {desbordamientos} desbordamiento(s) de audio.")
    return activaciones, horas, detector.puntuacion_maxima_con_voz


def main() -> int:
    opciones = crear_argumentos().parse_args()
    try:
        activaciones, horas, maxima = escuchar(opciones)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"No se pudo escuchar: {error}")
        return 1
    except Exception as error:
        print(f"El sistema de audio falló: {type(error).__name__}: {error}")
        return 1

    print()
    print(f"Duración: {horas * 60:.1f} min")
    print(f"Activaciones: {activaciones}")
    if horas > 0:
        print(f"Ritmo: {activaciones / horas:.2f} por hora")
    print(f"Puntuación máxima oída con voz: {maxima:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
