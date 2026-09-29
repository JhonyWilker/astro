from pathlib import Path

import numpy as np

from voice.vad_silero import RUTA_MODELOS_ACTIVACION


FRAMES_VENTANA = 16


def reenviar(
    capas: list[tuple[np.ndarray, np.ndarray]],
    media: np.ndarray,
    escala: np.ndarray,
    filas: np.ndarray,
) -> np.ndarray:
    """Red densa con ReLU y salida sigmoide. Devuelve una probabilidad por fila."""
    valores = (filas - media) / escala
    for indice, (pesos, sesgos) in enumerate(capas):
        valores = valores @ pesos + sesgos
        if indice < len(capas) - 1:
            valores = np.maximum(valores, 0.0)
    return (1.0 / (1.0 + np.exp(-valores))).reshape(-1)


def guardar_modelo(
    ruta: Path,
    capas: list[tuple[np.ndarray, np.ndarray]],
    media: np.ndarray,
    escala: np.ndarray,
) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = {"media": media, "escala": escala, "capas": np.array(len(capas))}
    for indice, (pesos, sesgos) in enumerate(capas):
        contenido[f"W{indice}"] = pesos
        contenido[f"b{indice}"] = sesgos
    np.savez_compressed(ruta, **contenido)


def cargar_parametros(
    ruta: Path,
) -> tuple[list[tuple[np.ndarray, np.ndarray]], np.ndarray, np.ndarray]:
    datos = np.load(ruta)
    capas = [
        (datos[f"W{indice}"], datos[f"b{indice}"])
        for indice in range(int(datos["capas"]))
    ]
    return capas, datos["media"], datos["escala"]


class ModeloAstro:
    """Modelo propio de activación: huellas de openWakeWord + red pequeña."""

    def __init__(self, ruta: Path, nombre: str = "astro") -> None:
        from openwakeword.utils import AudioFeatures

        self._nombre = nombre
        self._capas, self._media, self._escala = cargar_parametros(ruta)
        self._huellas = AudioFeatures(
            melspec_model_path=str(RUTA_MODELOS_ACTIVACION / "melspectrogram.onnx"),
            embedding_model_path=str(RUTA_MODELOS_ACTIVACION / "embedding_model.onnx"),
        )

    def reset(self) -> None:
        self._huellas.reset()

    def predict(self, bloque: np.ndarray) -> dict[str, float]:
        self._huellas(bloque)
        fila = self._huellas.get_features(FRAMES_VENTANA)[0].reshape(1, -1)
        probabilidad = reenviar(self._capas, self._media, self._escala, fila)
        return {self._nombre: float(probabilidad[0])}
