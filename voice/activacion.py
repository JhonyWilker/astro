import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any

import numpy as np

from voice.vad_silero import (
    MUESTRAS_BLOQUE as MUESTRAS_VAD,
    RAIZ_PROYECTO,
    RUTA_MODELOS_ACTIVACION,
    VadSilero,
)


RUTA_REGISTRO = RAIZ_PROYECTO / "logs" / "activaciones.jsonl"
FRECUENCIA_HZ = 16000
MUESTRAS_ACTIVACION = 1280
SEGUNDOS_BLOQUE_ACTIVACION = MUESTRAS_ACTIVACION / FRECUENCIA_HZ
SEGUNDOS_BLOQUE_VAD = MUESTRAS_VAD / FRECUENCIA_HZ
MODELO_ASTRO = RUTA_MODELOS_ACTIVACION / "astro_v1.npz"
AJUSTES_ASTRO = RUTA_MODELOS_ACTIVACION / "astro_v1.json"


@dataclass(frozen=True)
class ConfiguracionActivacion:
    ruta_modelo: Path = MODELO_ASTRO
    umbral: float = 0.5
    umbral_voz: float = 0.5
    ventana_voz: float = 1.0
    bloques_consecutivos: int = 1
    refractario: float = 2.0


@dataclass(frozen=True)
class Activacion:
    puntuacion: float
    modelo: str


def configuracion_predeterminada(
    ruta_explicita: Path | None = None,
) -> ConfiguracionActivacion:
    """Usa el modelo propio o una ruta elegida deliberadamente."""
    if ruta_explicita is not None:
        return ConfiguracionActivacion(ruta_modelo=ruta_explicita)
    if not MODELO_ASTRO.is_file():
        raise FileNotFoundError(
            f"Falta el modelo propio de «Astro»: {MODELO_ASTRO}. "
            "Entrénalo con python -m voice.entrenar_activacion o indica "
            "otro modelo deliberadamente."
        )
    ajustes = {}
    if AJUSTES_ASTRO.is_file():
        ajustes = json.loads(AJUSTES_ASTRO.read_text(encoding="utf-8"))
    return ConfiguracionActivacion(
        ruta_modelo=MODELO_ASTRO,
        umbral=float(ajustes.get("umbral", 0.9)),
        bloques_consecutivos=int(ajustes.get("bloques_consecutivos", 2)),
        umbral_voz=0.4,
    )


def registrar_activacion(
    activacion: Activacion,
    ruta: Path = RUTA_REGISTRO,
) -> None:
    """Guarda hora, modelo y puntuación; nunca el audio."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    linea = json.dumps(
        {
            "fecha": datetime.now(timezone.utc).isoformat(),
            "modelo": activacion.modelo,
            "puntuacion": round(activacion.puntuacion, 4),
        }
    )
    with ruta.open("a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")


def validar_configuracion(configuracion: ConfiguracionActivacion) -> None:
    if not 0 < configuracion.umbral <= 1:
        raise ValueError("El umbral de activación debe estar entre 0 y 1")
    if not 0 < configuracion.umbral_voz <= 1:
        raise ValueError("El umbral de voz debe estar entre 0 y 1")
    if not 0.2 <= configuracion.ventana_voz <= 5:
        raise ValueError("La ventana de voz debe estar entre 0,2 y 5 segundos")
    if not 1 <= configuracion.bloques_consecutivos <= 10:
        raise ValueError("Los bloques consecutivos deben estar entre 1 y 10")
    if not 0 <= configuracion.refractario <= 10:
        raise ValueError("El periodo de descanso debe estar entre 0 y 10 segundos")


def cargar_modelo_activacion(ruta_modelo: Path) -> Any:
    carpeta = RUTA_MODELOS_ACTIVACION
    necesarios = (
        ruta_modelo,
        carpeta / "melspectrogram.onnx",
        carpeta / "embedding_model.onnx",
    )
    for ruta in necesarios:
        if not ruta.is_file():
            raise FileNotFoundError(
                f"Falta un modelo de activación: {ruta}"
            )

    if ruta_modelo.suffix == ".npz":
        from voice.modelo_astro import ModeloAstro

        return ModeloAstro(ruta_modelo)

    from openwakeword.model import Model

    return Model(
        wakeword_models=[str(ruta_modelo)],
        inference_framework="onnx",
        melspec_model_path=str(carpeta / "melspectrogram.onnx"),
        embedding_model_path=str(carpeta / "embedding_model.onnx"),
    )


class DetectorActivacion:
    """Detecta la palabra de activación en audio continuo de 16 kHz.

    El modelo de activación recibe siempre todo el audio, porque necesita
    continuidad. La decisión solo cuenta si Silero oyó voz en la última
    ventana, lo que descarta música, ruido y silencio.
    """

    def __init__(
        self,
        configuracion: ConfiguracionActivacion = ConfiguracionActivacion(),
        modelo: Any | None = None,
        vad: VadSilero | None = None,
    ) -> None:
        validar_configuracion(configuracion)
        self.configuracion = configuracion
        self._modelo = modelo or cargar_modelo_activacion(
            configuracion.ruta_modelo
        )
        self._vad = vad or VadSilero()
        self._maxima_con_voz = 0.0
        self._bloques_ventana_voz = ceil(
            configuracion.ventana_voz / SEGUNDOS_BLOQUE_VAD
        )
        self._bloques_refractario = ceil(
            configuracion.refractario / SEGUNDOS_BLOQUE_ACTIVACION
        )
        self.reiniciar()

    def reiniciar(self) -> None:
        self._modelo.reset()
        self._vad.reiniciar()
        self._pendiente_vad = np.empty(0, dtype=np.int16)
        self._pendiente_modelo = np.empty(0, dtype=np.int16)
        self._bloques_sin_voz = self._bloques_ventana_voz
        self._consecutivos = 0
        self._descanso = 0

    @property
    def puntuacion_maxima_con_voz(self) -> float:
        return self._maxima_con_voz

    def alimentar(self, muestras: np.ndarray) -> Activacion | None:
        if muestras.dtype != np.int16:
            raise ValueError("El audio debe ser PCM de 16 bits")

        self._pendiente_vad = np.concatenate((self._pendiente_vad, muestras))
        while len(self._pendiente_vad) >= MUESTRAS_VAD:
            bloque = self._pendiente_vad[:MUESTRAS_VAD]
            self._pendiente_vad = self._pendiente_vad[MUESTRAS_VAD:]
            if (
                self._vad.probabilidad(bloque)
                >= self.configuracion.umbral_voz
            ):
                self._bloques_sin_voz = 0
            else:
                self._bloques_sin_voz += 1

        self._pendiente_modelo = np.concatenate(
            (self._pendiente_modelo, muestras)
        )
        activacion: Activacion | None = None
        while len(self._pendiente_modelo) >= MUESTRAS_ACTIVACION:
            bloque = self._pendiente_modelo[:MUESTRAS_ACTIVACION]
            self._pendiente_modelo = self._pendiente_modelo[
                MUESTRAS_ACTIVACION:
            ]
            resultado = self._evaluar(bloque)
            if resultado is not None and activacion is None:
                activacion = resultado
        return activacion

    def _evaluar(self, bloque: np.ndarray) -> Activacion | None:
        puntuaciones = self._modelo.predict(bloque)
        modelo, puntuacion = max(
            puntuaciones.items(), key=lambda elemento: elemento[1]
        )

        if self._descanso > 0:
            self._descanso -= 1
            self._consecutivos = 0
            return None

        hay_voz = self._bloques_sin_voz < self._bloques_ventana_voz
        if hay_voz:
            self._maxima_con_voz = max(self._maxima_con_voz, float(puntuacion))
        if hay_voz and puntuacion >= self.configuracion.umbral:
            self._consecutivos += 1
        else:
            self._consecutivos = 0

        if self._consecutivos < self.configuracion.bloques_consecutivos:
            return None

        self._consecutivos = 0
        self._descanso = self._bloques_refractario
        self._modelo.reset()
        return Activacion(puntuacion=float(puntuacion), modelo=str(modelo))
