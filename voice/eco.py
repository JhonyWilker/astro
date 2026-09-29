"""Envoltorio local de WebRTC AEC3."""

from typing import Any

import numpy as np


FRECUENCIA_ECO_HZ = 16000
MUESTRAS_ECO = 160


class CanceladorEco:
    """Aísla la API nativa de WebRTC del resto del cliente de voz."""

    def __init__(
        self,
        retardo_ms: int = 40,
        procesador: Any | None = None,
    ) -> None:
        if not 0 <= retardo_ms <= 500:
            raise ValueError("El retardo de eco debe estar entre 0 y 500 ms")
        if procesador is None:
            try:
                from pywebrtc_audio import AudioProcessor
            except ImportError as error:
                raise RuntimeError(
                    "Falta pywebrtc-audio. Instala requirements-voice.txt."
                ) from error
            procesador = AudioProcessor(
                sample_rate=FRECUENCIA_ECO_HZ,
                num_channels=1,
                echo_cancellation=True,
                noise_suppression=True,
                stream_delay_ms=retardo_ms,
            )
        self._procesador = procesador

    def procesar(
        self,
        microfono: np.ndarray,
        referencia: np.ndarray,
    ) -> np.ndarray:
        microfono = np.asarray(microfono, dtype=np.int16).reshape(-1)
        referencia = np.asarray(referencia, dtype=np.int16).reshape(-1)
        esperado = (MUESTRAS_ECO,)
        if microfono.shape != esperado or referencia.shape != esperado:
            raise ValueError(
                f"El cancelador necesita bloques de {MUESTRAS_ECO} muestras"
            )
        limpio = self._procesador.process(microfono, referencia)
        return np.asarray(limpio, dtype=np.int16)

    def reiniciar(self) -> None:
        self._procesador.reset()
