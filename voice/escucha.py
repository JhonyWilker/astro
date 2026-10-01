from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np

from clients.grabar_audio import (
    CANALES,
    FORMATO_MUESTRA,
    InformeAudio,
    analizar_wav,
    cargar_sounddevice,
    guardar_wav,
)
from voice.activacion import (
    Activacion,
    DetectorActivacion,
    FRECUENCIA_HZ,
    MUESTRAS_ACTIVACION,
    SEGUNDOS_BLOQUE_VAD,
)
from voice.vad_silero import MUESTRAS_BLOQUE as MUESTRAS_VAD, VadSilero


BLOQUES_VOZ_NECESARIOS = 2
BLOQUES_PREGRABACION = 8
BLOQUES_PREACTIVACION = 8


def nivel_visual_pcm(bloque: bytes | np.ndarray) -> float:
    """Convierte PCM16 en un nivel logarítmico estable entre 0 y 1."""
    muestras = (
        np.frombuffer(bloque, dtype=np.int16)
        if isinstance(bloque, bytes)
        else np.asarray(bloque, dtype=np.int16).reshape(-1)
    )
    if not muestras.size:
        return 0.0
    normalizadas = muestras.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(normalizadas))))
    decibelios = 20.0 * float(np.log10(max(rms, 1e-6)))
    return max(0.0, min(1.0, (decibelios + 60.0) / 60.0))


@dataclass(frozen=True)
class ConfiguracionFrase:
    espera_maxima: float = 5.0
    duracion_maxima: float = 30.0
    silencio_final: float = 0.5
    umbral_voz: float = 0.5


@dataclass(frozen=True)
class ResultadoEscucha:
    activacion: Activacion
    informe: InformeAudio
    desbordamientos: int


@dataclass(frozen=True)
class ResultadoFrase:
    informe: InformeAudio
    desbordamientos: int


def validar_configuracion(configuracion: ConfiguracionFrase) -> None:
    if not 0.1 <= configuracion.espera_maxima <= 60:
        raise ValueError("La espera máxima debe estar entre 0,1 y 60 segundos")
    if not 0.2 <= configuracion.duracion_maxima <= 60:
        raise ValueError("La duración máxima debe estar entre 0,2 y 60 segundos")
    if not 0.2 <= configuracion.silencio_final <= 3:
        raise ValueError("El silencio final debe estar entre 0,2 y 3 segundos")
    if not 0 < configuracion.umbral_voz <= 1:
        raise ValueError("El umbral de voz debe estar entre 0 y 1")


class EscuchaContinua:
    """Espera «Astro» y captura la frase siguiente con un solo micrófono."""

    def __init__(
        self,
        detector: DetectorActivacion,
        vad_frase: VadSilero | None = None,
        dispositivo: int | None = None,
        modulo_audio: Any | None = None,
        al_nivel: Callable[[float], None] | None = None,
    ) -> None:
        self._detector = detector
        self._vad = vad_frase or VadSilero()
        self._dispositivo = dispositivo
        self._audio = modulo_audio or cargar_sounddevice()
        self.al_nivel = al_nivel

    def _publicar_nivel(self, bloque: bytes) -> None:
        if self.al_nivel is None:
            return
        try:
            self.al_nivel(nivel_visual_pcm(bloque))
        except Exception:
            self.al_nivel = None

    def nombre_dispositivo(self) -> str:
        informacion = self._audio.query_devices(self._dispositivo, "input")
        return str(informacion["name"])

    def esperar_frase(
        self,
        salida: Path,
        configuracion: ConfiguracionFrase = ConfiguracionFrase(),
        cancelar: Event | None = None,
        al_activar: Callable[[Activacion], None] | None = None,
    ) -> ResultadoEscucha:
        validar_configuracion(configuracion)
        self._detector.reiniciar()
        self._vad.reiniciar()

        with self._audio.RawInputStream(
            samplerate=FRECUENCIA_HZ,
            device=self._dispositivo,
            channels=CANALES,
            dtype=FORMATO_MUESTRA,
        ) as flujo:
            activacion, desbordamientos, audio_inicial = self._esperar_activacion(
                flujo, cancelar
            )
            if al_activar is not None:
                al_activar(activacion)
            pcm, desbordados_frase = self._capturar_frase(
                flujo,
                configuracion,
                cancelar,
                audio_inicial=audio_inicial,
            )

        guardar_wav(salida, pcm, FRECUENCIA_HZ)
        return ResultadoEscucha(
            activacion=activacion,
            informe=analizar_wav(salida),
            desbordamientos=desbordamientos + desbordados_frase,
        )

    def esperar_seguimiento(
        self,
        salida: Path,
        configuracion: ConfiguracionFrase,
        cancelar: Event | None = None,
        audio_inicial: bytes = b"",
        voz_inicial_confirmada: bool = False,
    ) -> ResultadoFrase:
        """Captura una frase nueva sin exigir otra palabra de activación."""
        validar_configuracion(configuracion)
        self._vad.reiniciar()

        with self._audio.RawInputStream(
            samplerate=FRECUENCIA_HZ,
            device=self._dispositivo,
            channels=CANALES,
            dtype=FORMATO_MUESTRA,
        ) as flujo:
            pcm, desbordamientos = self._capturar_frase(
                flujo,
                configuracion,
                cancelar,
                audio_inicial=audio_inicial,
                voz_inicial_confirmada=voz_inicial_confirmada,
            )

        guardar_wav(salida, pcm, FRECUENCIA_HZ)
        return ResultadoFrase(
            informe=analizar_wav(salida),
            desbordamientos=desbordamientos,
        )

    def _esperar_activacion(
        self,
        flujo: Any,
        cancelar: Event | None,
    ) -> tuple[Activacion, int, bytes]:
        desbordamientos = 0
        preactivacion: deque[bytes] = deque(maxlen=BLOQUES_PREACTIVACION)
        while True:
            if cancelar is not None and cancelar.is_set():
                raise InterruptedError("Escucha cancelada")
            datos, desbordado = flujo.read(MUESTRAS_ACTIVACION)
            desbordamientos += int(desbordado)
            bloque = bytes(datos)
            self._publicar_nivel(bloque)
            preactivacion.append(bloque)
            activacion = self._detector.alimentar(
                np.frombuffer(bloque, dtype=np.int16)
            )
            if activacion is not None:
                return activacion, desbordamientos, b"".join(preactivacion)

    def _capturar_frase(
        self,
        flujo: Any,
        configuracion: ConfiguracionFrase,
        cancelar: Event | None,
        audio_inicial: bytes = b"",
        voz_inicial_confirmada: bool = False,
    ) -> tuple[bytes, int]:
        bloques_espera = ceil(
            configuracion.espera_maxima / SEGUNDOS_BLOQUE_VAD
        )
        bloques_maximos = ceil(
            configuracion.duracion_maxima / SEGUNDOS_BLOQUE_VAD
        )
        bloques_silencio = ceil(
            configuracion.silencio_final / SEGUNDOS_BLOQUE_VAD
        )

        pregrabacion: deque[bytes] = deque(maxlen=BLOQUES_PREGRABACION)
        fragmentos: list[bytes] = (
            [audio_inicial]
            if audio_inicial and voz_inicial_confirmada
            else []
        )
        desbordamientos = 0
        esperando = 0
        seguidos = 0
        silencio = 0
        voz_iniciada = bool(fragmentos)

        while True:
            if cancelar is not None and cancelar.is_set():
                raise InterruptedError("Escucha cancelada")
            datos, desbordado = flujo.read(MUESTRAS_VAD)
            desbordamientos += int(desbordado)
            bloque = bytes(datos)
            self._publicar_nivel(bloque)
            contiene_voz = (
                self._vad.probabilidad(np.frombuffer(bloque, dtype=np.int16))
                >= configuracion.umbral_voz
            )

            if not voz_iniciada:
                esperando += 1
                pregrabacion.append(bloque)
                seguidos = seguidos + 1 if contiene_voz else 0
                if seguidos >= BLOQUES_VOZ_NECESARIOS:
                    voz_iniciada = True
                    if audio_inicial:
                        fragmentos.append(audio_inicial)
                    fragmentos.extend(pregrabacion)
                elif esperando >= bloques_espera:
                    raise ValueError(
                        "No se detectó voz dentro del tiempo de espera"
                    )
                continue

            fragmentos.append(bloque)
            silencio = 0 if contiene_voz else silencio + 1
            if silencio >= bloques_silencio:
                break
            if len(fragmentos) >= bloques_maximos:
                break

        return b"".join(fragmentos), desbordamientos
