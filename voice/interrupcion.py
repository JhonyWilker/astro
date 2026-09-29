"""Detección y medición de interrupción, todavía para uso con auriculares."""

from dataclasses import dataclass, field
from threading import Event, Lock
from time import perf_counter
from typing import Any, Callable

import numpy as np

from clients.grabar_audio import cargar_sounddevice
from voice.vad_silero import FRECUENCIA_HZ, MUESTRAS_BLOQUE, VadSilero


@dataclass
class ControlInterrupcion:
    """Marca el corte entre los hilos del micrófono y del altavoz."""

    reloj: Callable[[], float] = perf_counter
    evento: Event = field(default_factory=Event)
    detectada_en: float | None = None
    detenida_en: float | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def detectar(self) -> bool:
        with self._lock:
            if self.evento.is_set():
                return False
            self.detectada_en = self.reloj()
            self.evento.set()
            return True

    def registrar_detencion(self) -> None:
        with self._lock:
            if self.detectada_en is not None and self.detenida_en is None:
                self.detenida_en = self.reloj()

    def is_set(self) -> bool:
        return self.evento.is_set()

    @property
    def latencia_segundos(self) -> float | None:
        if self.detectada_en is None or self.detenida_en is None:
            return None
        return max(0.0, self.detenida_en - self.detectada_en)


def escuchar_interrupcion(
    dispositivo: int | None,
    terminar: Event,
    hablando: Event,
    control: ControlInterrupcion,
    al_detectar: Callable[[], Any],
    *,
    vad: Any | None = None,
    modulo_audio: Any | None = None,
    umbral: float = 0.55,
    bloques_consecutivos: int = 3,
) -> None:
    if not 0 < umbral < 1:
        raise ValueError("El umbral de interrupción debe estar entre 0 y 1")
    if bloques_consecutivos < 1:
        raise ValueError("Hace falta al menos un bloque de voz")

    audio = modulo_audio or cargar_sounddevice()
    detector = vad or VadSilero()
    consecutivos = 0
    estaba_hablando = False
    with audio.RawInputStream(
        samplerate=FRECUENCIA_HZ,
        device=dispositivo,
        channels=1,
        dtype="int16",
    ) as flujo:
        while not terminar.is_set() and not control.is_set():
            datos, _ = flujo.read(MUESTRAS_BLOQUE)
            if not hablando.is_set():
                if estaba_hablando:
                    detector.reiniciar()
                estaba_hablando = False
                consecutivos = 0
                continue

            estaba_hablando = True
            bloque = np.frombuffer(bytes(datos), dtype=np.int16)
            if detector.probabilidad(bloque) >= umbral:
                consecutivos += 1
            else:
                consecutivos = 0
            if consecutivos >= bloques_consecutivos:
                if control.detectar():
                    al_detectar()
                return
