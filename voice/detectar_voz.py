from collections import deque
from dataclasses import dataclass
from math import ceil, sqrt
from pathlib import Path
from struct import iter_unpack
from typing import Any

from clients.grabar_audio import (
    BLOQUE_MUESTRAS,
    CANALES,
    FORMATO_MUESTRA,
    InformeAudio,
    analizar_wav,
    cargar_sounddevice,
    guardar_wav,
)


DURACION_BLOQUE = 0.03
UMBRAL_RMS_MINIMO = 150.0
FACTOR_RUIDO = 3.0
BLOQUES_VOZ_NECESARIOS = 3
VENTANA_INICIO = 5


@dataclass(frozen=True)
class ConfiguracionDeteccion:
    espera_maxima: float = 5.0
    duracion_maxima: float = 30.0
    silencio_final: float = 1.0
    pregrabacion: float = 0.3


def nivel_rms_pcm16(datos: bytes) -> float:
    muestras = tuple(valor[0] for valor in iter_unpack("<h", datos))
    if not muestras:
        return 0.0
    return sqrt(
        sum(valor * valor for valor in muestras) / len(muestras)
    )


def validar_configuracion(
    configuracion: ConfiguracionDeteccion,
) -> None:
    if not 0.1 <= configuracion.espera_maxima <= 60:
        raise ValueError(
            "La espera máxima debe estar entre 0,1 y 60 segundos"
        )
    if not 0.2 <= configuracion.duracion_maxima <= 60:
        raise ValueError(
            "La duración máxima debe estar entre 0,2 y 60 segundos"
        )
    if not 0.2 <= configuracion.silencio_final <= 3:
        raise ValueError(
            "El silencio final debe estar entre 0,2 y 3 segundos"
        )
    if not 0 <= configuracion.pregrabacion <= 1:
        raise ValueError(
            "La pregrabación debe estar entre 0 y 1 segundo"
        )


def grabar_hasta_silencio(
    salida: Path,
    dispositivo: int | None = None,
    configuracion: ConfiguracionDeteccion = ConfiguracionDeteccion(),
    modulo_audio: Any | None = None,
) -> tuple[InformeAudio, str, int]:
    validar_configuracion(configuracion)
    audio = modulo_audio or cargar_sounddevice()
    informacion = audio.query_devices(dispositivo, "input")
    frecuencia_hz = round(float(informacion["default_samplerate"]))
    muestras_bloque = min(
        BLOQUE_MUESTRAS,
        max(1, round(frecuencia_hz * DURACION_BLOQUE)),
    )

    bloques_espera = ceil(
        configuracion.espera_maxima * frecuencia_hz
        / muestras_bloque
    )
    bloques_maximos = ceil(
        configuracion.duracion_maxima * frecuencia_hz
        / muestras_bloque
    )
    bloques_silencio = ceil(
        configuracion.silencio_final * frecuencia_hz
        / muestras_bloque
    )
    bloques_previos = max(
        1,
        ceil(
            configuracion.pregrabacion * frecuencia_hz
            / muestras_bloque
        ),
    )

    pregrabacion: deque[bytes] = deque(maxlen=bloques_previos)
    ventana_inicio: deque[bool] = deque(maxlen=VENTANA_INICIO)
    fragmentos: list[bytes] = []
    nivel_ruido = 0.0
    esperando = 0
    grabados = 0
    silencio = 0
    desbordamientos = 0
    voz_iniciada = False

    with audio.RawInputStream(
        samplerate=frecuencia_hz,
        device=dispositivo,
        channels=CANALES,
        dtype=FORMATO_MUESTRA,
    ) as flujo:
        while True:
            datos, desbordado = flujo.read(muestras_bloque)
            bloque = bytes(datos)
            desbordamientos += int(desbordado)
            rms = nivel_rms_pcm16(bloque)
            umbral = max(
                UMBRAL_RMS_MINIMO,
                nivel_ruido * FACTOR_RUIDO,
            )
            contiene_voz = rms >= umbral

            if not voz_iniciada:
                esperando += 1
                pregrabacion.append(bloque)
                ventana_inicio.append(contiene_voz)
                if not contiene_voz:
                    nivel_ruido = (
                        rms
                        if nivel_ruido == 0
                        else nivel_ruido * 0.9 + rms * 0.1
                    )

                if (
                    len(ventana_inicio) >= BLOQUES_VOZ_NECESARIOS
                    and sum(ventana_inicio)
                    >= BLOQUES_VOZ_NECESARIOS
                ):
                    voz_iniciada = True
                    fragmentos.extend(pregrabacion)
                    grabados = len(fragmentos)
                elif esperando >= bloques_espera:
                    raise ValueError(
                        "No se detectó voz dentro del tiempo de espera"
                    )
                continue

            fragmentos.append(bloque)
            grabados += 1
            if contiene_voz:
                silencio = 0
            else:
                silencio += 1

            if silencio >= bloques_silencio:
                break
            if grabados >= bloques_maximos:
                break

    guardar_wav(salida, b"".join(fragmentos), frecuencia_hz)
    return (
        analizar_wav(salida),
        str(informacion["name"]),
        desbordamientos,
    )
