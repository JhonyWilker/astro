from pathlib import Path
from typing import Any

import numpy as np


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_MODELOS_ACTIVACION = RAIZ_PROYECTO / "data" / "models" / "wakeword"
RUTA_MODELO_VAD = RUTA_MODELOS_ACTIVACION / "silero_vad.onnx"
FRECUENCIA_HZ = 16000
MUESTRAS_BLOQUE = 512


class VadSilero:
    """Probabilidad de voz por bloque de 32 ms con Silero VAD en ONNX."""

    def __init__(
        self,
        ruta_modelo: Path = RUTA_MODELO_VAD,
        sesion: Any | None = None,
    ) -> None:
        if sesion is None:
            if not ruta_modelo.is_file():
                raise FileNotFoundError(
                    f"Falta el modelo de detección de voz: {ruta_modelo}"
                )
            import onnxruntime

            opciones = onnxruntime.SessionOptions()
            opciones.intra_op_num_threads = 1
            opciones.inter_op_num_threads = 1
            sesion = onnxruntime.InferenceSession(
                str(ruta_modelo),
                sess_options=opciones,
                providers=["CPUExecutionProvider"],
            )
        self._sesion = sesion
        self._frecuencia = np.array(FRECUENCIA_HZ, dtype=np.int64)
        self.reiniciar()

    def reiniciar(self) -> None:
        self._h = np.zeros((2, 1, 64), dtype=np.float32)
        self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def probabilidad(self, bloque: np.ndarray) -> float:
        if bloque.shape != (MUESTRAS_BLOQUE,):
            raise ValueError(
                f"El bloque debe tener {MUESTRAS_BLOQUE} muestras"
            )
        entrada = (bloque.astype(np.float32) / 32768.0)[np.newaxis, :]
        salida, self._h, self._c = self._sesion.run(
            None,
            {
                "input": entrada,
                "sr": self._frecuencia,
                "h": self._h,
                "c": self._c,
            },
        )
        return float(salida[0][0])
