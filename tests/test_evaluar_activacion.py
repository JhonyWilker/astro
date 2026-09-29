import numpy as np

from voice.activacion import ConfiguracionActivacion, DetectorActivacion
from voice.evaluar_activacion import (
    activaciones_en,
    evaluar_falsas,
    rodear_de_silencio,
)


class ModeloFalso:
    def __init__(self, puntuaciones):
        self.puntuaciones = list(puntuaciones)
        self.indice = 0

    def reset(self) -> None:
        return None

    def predict(self, bloque):
        valor = self.puntuaciones[self.indice] if self.indice < len(self.puntuaciones) else 0.0
        self.indice += 1
        return {"astro": valor}


class VadFalso:
    def reiniciar(self) -> None:
        return None

    def probabilidad(self, bloque) -> float:
        return 1.0


def crear_detector(puntuaciones) -> DetectorActivacion:
    return DetectorActivacion(
        ConfiguracionActivacion(refractario=0.0),
        modelo=ModeloFalso(puntuaciones),
        vad=VadFalso(),
    )


def test_devuelve_el_segundo_de_cada_activacion() -> None:
    detector = crear_detector([0.0, 0.0, 0.9])
    señal = np.zeros(1280 * 5, dtype=np.int16)

    assert activaciones_en(detector, señal) == [0.24]


def test_no_devuelve_nada_si_el_modelo_no_puntua_alto() -> None:
    detector = crear_detector([0.1] * 5)

    assert activaciones_en(detector, np.zeros(1280 * 5, dtype=np.int16)) == []


def test_falsas_devuelve_cantidad_y_horas() -> None:
    detector = crear_detector([0.9, 0.0, 0.9])
    flujo = np.zeros(16000 * 36, dtype=np.int16)

    falsas, horas = evaluar_falsas(detector, flujo)

    assert falsas == 2
    assert horas == 36 / 3600


def test_rodear_de_silencio_anade_margenes() -> None:
    clip = np.full(16000, 1000, dtype=np.int16)

    resultado = rodear_de_silencio(clip, np.random.default_rng(0))

    assert len(resultado) == 16000 + int(1.6 * 16000) + int(1.2 * 16000)
    assert np.array_equal(resultado[int(1.6 * 16000):][:16000], clip)
