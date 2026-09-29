from collections import deque

import numpy as np
import pytest

from voice.eco import MUESTRAS_ECO
from voice.interrupcion import ControlInterrupcion, DetectorInterrupcionEco
from voice.vad_silero import MUESTRAS_BLOQUE


class CanceladorFalso:
    def __init__(self, valor=7):
        self.valor = valor
        self.llamadas = []

    def procesar(self, microfono, referencia):
        self.llamadas.append((microfono.copy(), referencia.copy()))
        return np.full(MUESTRAS_ECO, self.valor, dtype=np.int16)


class VadFalso:
    def __init__(self, probabilidades):
        self.probabilidades = iter(probabilidades)
        self.bloques = []
        self.reinicios = 0

    def probabilidad(self, bloque):
        assert bloque.shape == (MUESTRAS_BLOQUE,)
        self.bloques.append(bloque.copy())
        return next(self.probabilidades)

    def reiniciar(self):
        self.reinicios += 1


def test_detector_confirma_tres_bloques_limpios_consecutivos() -> None:
    cancelador = CanceladorFalso()
    vad = VadFalso([0.8, 0.2, 0.9, 0.9, 0.9])
    detector = DetectorInterrupcionEco(cancelador, vad=vad)
    detectado = False

    for _ in range(16):
        detectado = detector.procesar(
            np.zeros(MUESTRAS_ECO, dtype=np.int16),
            np.ones(MUESTRAS_ECO, dtype=np.int16),
        )
        if detectado:
            break

    assert detectado is True
    assert len(cancelador.llamadas) == 16
    assert len(vad.bloques) == 5


def test_detector_reinicia_solo_el_turno_no_el_cancelador() -> None:
    cancelador = CanceladorFalso()
    vad = VadFalso([0.9])
    detector = DetectorInterrupcionEco(cancelador, vad=vad)

    detector.preparar_fragmento()

    assert vad.reinicios == 1
    assert not hasattr(cancelador, "reiniciar")


def test_control_mide_desde_deteccion_hasta_detencion() -> None:
    tiempos = deque([10.0, 10.12])
    control = ControlInterrupcion(reloj=tiempos.popleft)

    assert control.detectar() is True
    assert control.detectar() is False
    control.registrar_detencion()

    assert control.latencia_segundos == pytest.approx(0.12)
