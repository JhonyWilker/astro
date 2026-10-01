"""Estados visibles y señales sonoras del cliente de voz de ASTRO."""

from collections.abc import Callable
from enum import Enum
from threading import Lock
from typing import Any

import numpy as np

from clients.grabar_audio import cargar_sounddevice


FRECUENCIA_SENAL_HZ = 16000
DURACION_TONO = 0.055
DURACION_PAUSA = 0.025
VOLUMEN_SENAL = 0.10


class EstadoVoz(str, Enum):
    MICROFONO_APAGADO = "microfono_apagado"
    DORMIDO = "dormido"
    ESCUCHANDO = "escuchando"
    PENSANDO = "pensando"
    EJECUTANDO = "ejecutando"
    HABLANDO = "hablando"


ETIQUETAS = {
    EstadoVoz.MICROFONO_APAGADO: "Micrófono apagado",
    EstadoVoz.DORMIDO: "Esperando «Astro»",
    EstadoVoz.ESCUCHANDO: "Habla ahora",
    EstadoVoz.PENSANDO: "Preparando respuesta",
    EstadoVoz.EJECUTANDO: "Usando una herramienta",
    EstadoVoz.HABLANDO: "Respondiendo",
}

SENALES = {
    EstadoVoz.MICROFONO_APAGADO: (330, 220),
    EstadoVoz.DORMIDO: (440, 330),
    EstadoVoz.ESCUCHANDO: (660, 880),
    EstadoVoz.PENSANDO: (440, 440),
    EstadoVoz.EJECUTANDO: (520, 660, 780),
    EstadoVoz.HABLANDO: (880,),
}

TRANSICIONES = {
    EstadoVoz.MICROFONO_APAGADO: {EstadoVoz.DORMIDO},
    EstadoVoz.DORMIDO: {EstadoVoz.ESCUCHANDO},
    EstadoVoz.ESCUCHANDO: {EstadoVoz.PENSANDO},
    EstadoVoz.PENSANDO: {
        EstadoVoz.EJECUTANDO,
        EstadoVoz.HABLANDO,
        EstadoVoz.ESCUCHANDO,
    },
    EstadoVoz.EJECUTANDO: {EstadoVoz.PENSANDO},
    EstadoVoz.HABLANDO: {EstadoVoz.ESCUCHANDO},
}


def generar_senal(estado: EstadoVoz) -> np.ndarray:
    """Genera una señal mono PCM16 corta y con entrada/salida suaves."""
    partes: list[np.ndarray] = []
    cantidad = round(FRECUENCIA_SENAL_HZ * DURACION_TONO)
    tiempo = np.arange(cantidad, dtype=np.float32) / FRECUENCIA_SENAL_HZ
    rampa = max(1, round(FRECUENCIA_SENAL_HZ * 0.006))
    envolvente = np.ones(cantidad, dtype=np.float32)
    envolvente[:rampa] = np.linspace(0, 1, rampa, dtype=np.float32)
    envolvente[-rampa:] = np.linspace(1, 0, rampa, dtype=np.float32)
    pausa = np.zeros(
        round(FRECUENCIA_SENAL_HZ * DURACION_PAUSA),
        dtype=np.int16,
    )

    for indice, frecuencia in enumerate(SENALES[estado]):
        onda = np.sin(2 * np.pi * frecuencia * tiempo)
        partes.append(
            (onda * envolvente * 32767 * VOLUMEN_SENAL).astype(np.int16)
        )
        if indice + 1 < len(SENALES[estado]):
            partes.append(pausa)
    return np.concatenate(partes)


def reproducir_senal(
    estado: EstadoVoz,
    dispositivo: int | None = None,
    modulo_audio: Any | None = None,
) -> None:
    audio = modulo_audio or cargar_sounddevice()
    pcm = generar_senal(estado)
    with audio.RawOutputStream(
        samplerate=FRECUENCIA_SENAL_HZ,
        device=dispositivo,
        channels=1,
        dtype="int16",
    ) as flujo:
        flujo.write(pcm.tobytes())


class IndicadorEstados:
    """Publica y valida el estado; el sonido nunca derriba la conversación."""

    def __init__(
        self,
        dispositivo: int | None = None,
        sonidos: bool = True,
        salida: Callable[[str], None] = print,
        reproductor: Callable[[EstadoVoz, int | None], None] = reproducir_senal,
        al_cambiar: Callable[[EstadoVoz, str], None] | None = None,
    ) -> None:
        self.estado: EstadoVoz | None = None
        self._dispositivo = dispositivo
        self._sonidos = sonidos
        self._salida = salida
        self._reproductor = reproductor
        self._bloqueo = Lock()
        self.al_cambiar = al_cambiar

    def cambiar(
        self,
        nuevo: EstadoVoz,
        detalle: str | None = None,
        *,
        sonido: bool = True,
    ) -> bool:
        with self._bloqueo:
            if nuevo == self.estado:
                return False
            if (
                self.estado is not None
                and nuevo not in {
                    EstadoVoz.DORMIDO,
                    EstadoVoz.MICROFONO_APAGADO,
                }
                and nuevo not in TRANSICIONES[self.estado]
            ):
                raise ValueError(
                    f"Transición de voz imposible: "
                    f"{self.estado.value} -> {nuevo.value}"
                )

            self.estado = nuevo
            texto = detalle or ETIQUETAS[nuevo]
            self._salida(f"[{nuevo.value.upper()}] {texto}")
            if self.al_cambiar is not None:
                try:
                    self.al_cambiar(nuevo, texto)
                except Exception:
                    self.al_cambiar = None  # un gancho roto nunca derriba la voz
            if self._sonidos and sonido:
                try:
                    self._reproductor(nuevo, self._dispositivo)
                except Exception as error:
                    self._sonidos = False
                    self._salida(
                        "[AVISO] Las señales de estado se desactivaron: "
                        f"{type(error).__name__}."
                    )
            return True
