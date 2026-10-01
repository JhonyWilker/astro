"""Detección y medición de interrupción sobre audio sin eco."""

from collections import deque
from dataclasses import dataclass, field
import re
from threading import Event, Lock
from time import perf_counter
from typing import Any, Callable
import unicodedata

import numpy as np

from voice.vad_silero import MUESTRAS_BLOQUE, VadSilero


BLOQUES_AUDIO_INTERRUPCION = 30
ORDENES_SILENCIO = {
    "sh", "shh", "shhh", "shhhh", "callate", "callate ya", "silencio",
    "silencio ya", "para", "para ya", "parate", "parate ya", "basta",
    "basta ya", "no hables", "deja de hablar", "guarda silencio",
    "haz silencio", "quieto", "quieto ya",
}


def es_orden_silencio(texto: str) -> bool:
    """Reconoce localmente una orden breve que debe dormir a ASTRO."""
    normalizado = unicodedata.normalize("NFKD", texto.casefold())
    normalizado = "".join(
        caracter for caracter in normalizado
        if not unicodedata.combining(caracter)
    )
    normalizado = re.sub(r"[^a-z\s]", "", normalizado)
    normalizado = " ".join(normalizado.split())
    return normalizado in ORDENES_SILENCIO


def transcripcion_interrupcion_fiable(resultado: Any) -> bool:
    """Evita convertir eco o una alucinación de Whisper en otro turno."""
    texto = getattr(resultado, "texto", "").strip()
    if len(re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]", texto)) < 2:
        return False
    if float(getattr(resultado, "probabilidad_idioma", 0.0)) < 0.35:
        return False
    segmentos = tuple(getattr(resultado, "segmentos", ()))
    if not segmentos:
        return False
    duracion_hablada = sum(
        max(0.0, float(segmento.fin) - float(segmento.inicio))
        for segmento in segmentos
    )
    if duracion_hablada < 0.15:
        return False
    return True


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
        umbral: float = 0.80,
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
        self._audio_reciente: deque[np.ndarray] = deque(
            maxlen=BLOQUES_AUDIO_INTERRUPCION
        )
        self._audio_interrupcion = b""
        self._retardo_ms: float | None = None

    def preparar_fragmento(self) -> None:
        self._pendientes = np.empty(0, dtype=np.int16)
        self._consecutivos = 0
        self._audio_reciente.clear()
        self._audio_interrupcion = b""
        self.vad.reiniciar()

    def actualizar_retardo(self, retardo_ms: float) -> int | None:
        """Suaviza el retardo real de PortAudio antes de pasarlo al AEC."""
        if not hasattr(self.cancelador, "actualizar_retardo"):
            return None
        if self._retardo_ms is None:
            self._retardo_ms = retardo_ms
        else:
            self._retardo_ms = self._retardo_ms * 0.8 + retardo_ms * 0.2
        return self.cancelador.actualizar_retardo(self._retardo_ms)

    def procesar(self, microfono: np.ndarray, referencia: np.ndarray) -> bool:
        limpio = self.cancelador.procesar(microfono, referencia)
        self._audio_reciente.append(limpio.copy())
        self._pendientes = np.concatenate((self._pendientes, limpio))
        while len(self._pendientes) >= MUESTRAS_BLOQUE:
            bloque = self._pendientes[:MUESTRAS_BLOQUE]
            self._pendientes = self._pendientes[MUESTRAS_BLOQUE:]
            if self.vad.probabilidad(bloque) >= self.umbral:
                self._consecutivos += 1
            else:
                self._consecutivos = 0
            if self._consecutivos >= self.bloques_consecutivos:
                self._audio_interrupcion = np.concatenate(
                    tuple(self._audio_reciente)
                ).astype(np.int16, copy=False).tobytes()
                return True
        return False

    def extraer_audio_interrupcion(self) -> bytes:
        return self._audio_interrupcion
