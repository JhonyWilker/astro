"""Detección y medición de interrupción sobre audio sin eco."""

from dataclasses import dataclass, field
from threading import Event, Lock
from time import perf_counter
from typing import Any, Callable

import numpy as np

from voice.vad_silero import MUESTRAS_BLOQUE, VadSilero


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


class DetectorInterrupcionEco:
    """Confirma voz humana después de retirar el audio de ASTRO."""

    def __init__(
        self,
        cancelador: Any,
        *,
        vad: Any | None = None,
        umbral: float = 0.70,
        bloques_consecutivos: int = 3,
    ) -> None:
        if not 0 < umbral < 1:
            raise ValueError("El umbral de interrupción debe estar entre 0 y 1")
        if bloques_consecutivos < 1:
            raise ValueError("Hace falta al menos un bloque de voz")
        self.cancelador = cancelador
        self.vad = vad or VadSilero()
        self.umbral = umbral
        self.bloques_consecutivos = bloques_consecutivos
        self._pendientes = np.empty(0, dtype=np.int16)
        self._consecutivos = 0

    def preparar_fragmento(self) -> None:
        self._pendientes = np.empty(0, dtype=np.int16)
        self._consecutivos = 0
        self.vad.reiniciar()

    def procesar(self, microfono: np.ndarray, referencia: np.ndarray) -> bool:
        limpio = self.cancelador.procesar(microfono, referencia)
        self._pendientes = np.concatenate((self._pendientes, limpio))
        while len(self._pendientes) >= MUESTRAS_BLOQUE:
            bloque = self._pendientes[:MUESTRAS_BLOQUE]
            self._pendientes = self._pendientes[MUESTRAS_BLOQUE:]
            if self.vad.probabilidad(bloque) >= self.umbral:
                self._consecutivos += 1
            else:
                self._consecutivos = 0
            if self._consecutivos >= self.bloques_consecutivos:
                return True
        return False
