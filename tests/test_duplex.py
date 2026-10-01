import numpy as np
import pytest
from queue import Queue
from threading import Event

from voice.duplex import reproducir_duplex, reproducir_pcm_streaming
from voice.eco import MUESTRAS_ECO
from voice.interrupcion import ControlInterrupcion
from voice.proveedor_voz import BloquePCM


class CallbackStop(Exception):
    pass


class CallbackAbort(Exception):
    pass


class DetectorFalso:
    def __init__(self, detectar=False):
        self.detectar = detectar
        self.pares = []
        self.preparaciones = 0
        self.retardos = []

    def preparar_fragmento(self):
        self.preparaciones += 1

    def procesar(self, microfono, referencia):
        self.pares.append((microfono.copy(), referencia.copy()))
        return self.detectar

    def actualizar_retardo(self, retardo_ms):
        self.retardos.append(retardo_ms)


class FlujoFalso:
    def __init__(self, audio, opciones):
        self.audio = audio
        self.opciones = opciones
        self.abortado = False

    def __enter__(self):
        callback = self.opciones["callback"]
        tiempo = type(
            "Tiempo",
            (),
            {"inputBufferAdcTime": 10.0, "outputBufferDacTime": 10.075},
        )()
        for numero in range(20):
            entrada = np.full((MUESTRAS_ECO, 1), numero + 1, dtype=np.int16)
            salida = np.zeros((MUESTRAS_ECO, 1), dtype=np.int16)
            try:
                callback(entrada, salida, MUESTRAS_ECO, tiempo, False)
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
    assert detector.retardos[0] == pytest.approx(75.0)


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


class FlujoSalidaStreamingFalso:
    def __init__(self):
        self.datos = bytearray()
        self.abortado = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, datos):
        self.datos.extend(datos)
        return False

    def abort(self):
        self.abortado = True


class AudioSalidaStreamingFalso:
    def __init__(self):
        self.flujo = FlujoSalidaStreamingFalso()
        self.opciones = None

    def RawOutputStream(self, **opciones):
        self.opciones = opciones
        return self.flujo


def test_pcm_streaming_reproduce_y_confirma_sin_wav() -> None:
    cola = Queue()
    pcm = b"\x03\x00" * 320
    cola.put(BloquePCM(pcm[:320]))
    cola.put(BloquePCM(pcm[320:]))
    cola.put(BloquePCM(b"", 25, True))
    cola.put(None)
    audio = AudioSalidaStreamingFalso()
    primeros = []
    confirmados = []

    fragmentos, cortes = reproducir_pcm_streaming(
        cola,
        16000,
        None,
        4,
        Event(),
        lambda: primeros.append(True),
        confirmados.append,
        modulo_audio=audio,
    )

    assert audio.opciones["device"] == 4
    assert bytes(audio.flujo.datos) == pcm
    assert primeros == [True]
    assert confirmados == [25]
    assert fragmentos == 1
    assert cortes == 0


def test_pcm_streaming_alinea_entrada_y_salida_en_un_callback() -> None:
    cola = Queue()
    muestras = np.arange(MUESTRAS_ECO * 12, dtype=np.int16)
    cola.put(BloquePCM(muestras.tobytes()))
    cola.put(BloquePCM(b"", 24, True))
    cola.put(None)
    audio = AudioFalso()
    detector = DetectorFalso()
    confirmados = []

    fragmentos, cortes = reproducir_pcm_streaming(
        cola,
        16000,
        2,
        3,
        ControlInterrupcion(),
        lambda: None,
        confirmados.append,
        detector,
        lambda: None,
        modulo_audio=audio,
    )

    assert detector.preparaciones == 1
    assert np.array_equal(detector.pares[0][1], muestras[:MUESTRAS_ECO])
    assert np.array_equal(audio.salidas[0][:, 0], muestras[:MUESTRAS_ECO])
    assert detector.retardos[0] == pytest.approx(75.0)
    assert confirmados == [24]
    assert fragmentos == 1
    assert cortes == 0
    assert audio.flujo.abortado is False
