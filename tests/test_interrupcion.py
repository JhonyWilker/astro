from collections import deque
from threading import Event

import numpy as np
import pytest

from voice.interrupcion import ControlInterrupcion, escuchar_interrupcion
from voice.vad_silero import MUESTRAS_BLOQUE


class VadFalso:
    def __init__(self, probabilidades):
        self.probabilidades = iter(probabilidades)
        self.reinicios = 0

    def probabilidad(self, bloque):
        assert bloque.shape == (MUESTRAS_BLOQUE,)
        return next(self.probabilidades)

    def reiniciar(self):
        self.reinicios += 1


class FlujoFalso:
    def __init__(self, al_leer=None):
        self.al_leer = al_leer

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, muestras):
        assert muestras == MUESTRAS_BLOQUE
        if self.al_leer:
            self.al_leer()
        return np.zeros(muestras, dtype=np.int16).tobytes(), False


class AudioFalso:
    def __init__(self, flujo):
        self.flujo = flujo
        self.argumentos = None

    def RawInputStream(self, **argumentos):
        self.argumentos = argumentos
        return self.flujo


def test_interrupcion_exige_tres_bloques_de_voz_consecutivos() -> None:
    hablando = Event()
    hablando.set()
    control = ControlInterrupcion()
    detectadas = []
    audio = AudioFalso(FlujoFalso())

    escuchar_interrupcion(
        2,
        Event(),
        hablando,
        control,
        lambda: detectadas.append(True),
        vad=VadFalso([0.8, 0.2, 0.9, 0.9, 0.9]),
        modulo_audio=audio,
    )

    assert detectadas == [True]
    assert control.is_set()
    assert audio.argumentos["samplerate"] == 16000
    assert audio.argumentos["device"] == 2


def test_interrupcion_ignora_voz_antes_de_que_astro_hable() -> None:
    hablando = Event()
    lecturas = 0

    def al_leer():
        nonlocal lecturas
        lecturas += 1
        if lecturas == 2:
            hablando.set()

    control = ControlInterrupcion()
    vad = VadFalso([0.9, 0.9, 0.9])

    escuchar_interrupcion(
        None,
        Event(),
        hablando,
        control,
        lambda: None,
        vad=vad,
        modulo_audio=AudioFalso(FlujoFalso(al_leer)),
    )

    assert lecturas == 4
    assert control.is_set()


def test_control_mide_desde_deteccion_hasta_detencion() -> None:
    tiempos = deque([10.0, 10.12])
    control = ControlInterrupcion(reloj=tiempos.popleft)

    assert control.detectar() is True
    assert control.detectar() is False
    control.registrar_detencion()

    assert control.latencia_segundos == pytest.approx(0.12)
