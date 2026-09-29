import numpy as np

from voice.duplex import reproducir_duplex
from voice.eco import MUESTRAS_ECO
from voice.interrupcion import ControlInterrupcion


class CallbackStop(Exception):
    pass


class CallbackAbort(Exception):
    pass


class DetectorFalso:
    def __init__(self, detectar=False):
        self.detectar = detectar
        self.pares = []
        self.preparaciones = 0

    def preparar_fragmento(self):
        self.preparaciones += 1

    def procesar(self, microfono, referencia):
        self.pares.append((microfono.copy(), referencia.copy()))
        return self.detectar


class FlujoFalso:
    def __init__(self, audio, opciones):
        self.audio = audio
        self.opciones = opciones
        self.abortado = False

    def __enter__(self):
        callback = self.opciones["callback"]
        for numero in range(20):
            entrada = np.full((MUESTRAS_ECO, 1), numero + 1, dtype=np.int16)
            salida = np.zeros((MUESTRAS_ECO, 1), dtype=np.int16)
            try:
                callback(entrada, salida, MUESTRAS_ECO, None, False)
            except (CallbackStop, CallbackAbort) as fin:
                self.abortado = isinstance(fin, CallbackAbort)
                self.audio.salidas.append(salida.copy())
                self.opciones["finished_callback"]()
                break
            self.audio.salidas.append(salida.copy())
        return self

    def __exit__(self, *args):
        return False

    def abort(self):
        self.abortado = True


class AudioFalso:
    CallbackStop = CallbackStop
    CallbackAbort = CallbackAbort

    def __init__(self):
        self.default = type("Default", (), {"device": (1, 4)})()
        self.opciones = None
        self.salidas = []
        self.flujo = None

    def Stream(self, **opciones):
        self.opciones = opciones
        self.flujo = FlujoFalso(self, opciones)
        return self.flujo


def test_duplex_empareja_microfono_y_bloque_reproducido() -> None:
    audio = AudioFalso()
    detector = DetectorFalso()
    muestras = np.arange(MUESTRAS_ECO * 2, dtype=np.int16)

    reproducir_duplex(
        muestras, 2, 3, detector, ControlInterrupcion(), lambda: None,
        modulo_audio=audio,
    )

    assert detector.preparaciones == 1
    assert audio.opciones["device"] == (2, 3)
    assert audio.opciones["blocksize"] == MUESTRAS_ECO
    assert np.array_equal(detector.pares[0][1], muestras[:MUESTRAS_ECO])
    assert np.array_equal(audio.salidas[0][:, 0], muestras[:MUESTRAS_ECO])


def test_duplex_aborta_y_avisa_al_detectar_voz() -> None:
    audio = AudioFalso()
    detector = DetectorFalso(detectar=True)
    control = ControlInterrupcion()
    avisos = []

    reproducir_duplex(
        np.ones(MUESTRAS_ECO * 3, dtype=np.int16),
        None, None, detector, control, lambda: avisos.append(True),
        modulo_audio=audio,
    )

    assert avisos == [True]
    assert control.is_set()
    assert control.latencia_segundos is not None
    assert audio.flujo.abortado is True
    assert np.count_nonzero(audio.salidas[0]) == 0
