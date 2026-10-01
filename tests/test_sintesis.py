from pathlib import Path
from struct import pack

import numpy as np
import pytest

from voice.hablar import (
    crear_configuracion,
    reproducir_wav,
    sintetizar,
)
from voice.interrupcion import ControlInterrupcion


class VozFalsa:
    def synthesize_wav(self, texto, archivo, syn_config):
        assert texto == "Hola, Jhony."
        assert syn_config == {"speaker_id": 0}
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(22050)
        archivo.writeframes(pack("<h", 1000) * 2205)


class FlujoSalidaFalso:
    def __init__(self, al_escribir=None):
        self.datos = b""
        self.al_escribir = al_escribir
        self.abortado = False
        self.tamanos = []

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback) -> None:
        return None

    def write(self, datos: bytes) -> bool:
        self.datos += bytes(datos)
        self.tamanos.append(len(datos))
        if self.al_escribir:
            self.al_escribir()
        return False

    def abort(self) -> None:
        self.abortado = True


class AudioSalidaFalso:
    def __init__(self):
        self.opciones = {}
        self.flujo = FlujoSalidaFalso()

    def RawOutputStream(self, **opciones):
        self.opciones = opciones
        return self.flujo


def test_sintetizar_crea_wav_pcm16(tmp_path: Path) -> None:
    salida = tmp_path / "respuesta.wav"
    tiempos = iter([10.0, 10.04])

    informe = sintetizar(
        "Hola, Jhony.",
        VozFalsa(),
        {"speaker_id": 0},
        salida,
        reloj=lambda: next(tiempos),
    )

    assert salida.exists()
    assert informe.duracion_audio == pytest.approx(0.1)
    assert informe.duracion_proceso == pytest.approx(0.04)
    assert informe.frecuencia_hz == 22050
    assert informe.canales == 1
    assert informe.bits_por_muestra == 16


def test_crear_configuracion_elige_hablante_masculino() -> None:
    configuracion = crear_configuracion(
        "M",
        fabrica=lambda **opciones: opciones,
    )

    assert configuracion == {"speaker_id": 0}


def test_reproducir_wav_usa_su_formato(tmp_path: Path) -> None:
    salida = tmp_path / "respuesta.wav"
    sintetizar(
        "Hola, Jhony.",
        VozFalsa(),
        {"speaker_id": 0},
        salida,
    )
    audio = AudioSalidaFalso()

    desbordado = reproducir_wav(
        salida,
        dispositivo=3,
        modulo_audio=audio,
    )

    assert desbordado is False
    assert audio.opciones == {
        "samplerate": 22050,
        "device": 3,
        "channels": 1,
        "dtype": "int16",
    }
    assert len(audio.flujo.datos) == 4410


def test_reproducir_wav_aborta_y_mide_una_interrupcion(tmp_path: Path) -> None:
    salida = tmp_path / "respuesta.wav"
    sintetizar(
        "Hola, Jhony.",
        VozFalsa(),
        {"speaker_id": 0},
        salida,
    )
    tiempos = iter([10.0, 10.02])
    control = ControlInterrupcion(reloj=lambda: next(tiempos))
    audio = AudioSalidaFalso()
    audio.flujo = FlujoSalidaFalso(control.detectar)

    reproducir_wav(
        salida,
        modulo_audio=audio,
        detener=control,
    )

    assert audio.flujo.abortado is True
    assert len(audio.flujo.datos) < 4410
    assert control.latencia_segundos == pytest.approx(0.02)


def test_reproducir_wav_usa_duplex_a_16_khz(tmp_path: Path, monkeypatch) -> None:
    salida = tmp_path / "respuesta.wav"
    sintetizar(
        "Hola, Jhony.",
        VozFalsa(),
        {"speaker_id": 0},
        salida,
    )
    llamadas = []

    def duplex(muestras, microfono, altavoz, detector, control, al_detectar,
               al_primer_audio, *, modulo_audio):
        llamadas.append((muestras, microfono, altavoz, detector, control,
                         al_detectar, al_primer_audio, modulo_audio))
        return False

    monkeypatch.setattr("voice.duplex.reproducir_duplex", duplex)
    audio = AudioSalidaFalso()
    control = ControlInterrupcion()
    detector = object()
    aviso = lambda: None

    reproducir_wav(
        salida,
        dispositivo=3,
        modulo_audio=audio,
        detener=control,
        microfono=2,
        detector_eco=detector,
        al_detectar=aviso,
    )

    llamada = llamadas[0]
    assert llamada[0].dtype == np.int16
    assert len(llamada[0]) == 1600
    assert llamada[1:3] == (2, 3)
    assert llamada[3] is detector
    assert llamada[4] is control
    assert llamada[5] is aviso
    assert llamada[6] is None
    assert llamada[7] is audio


def test_sintetizar_rechaza_texto_vacio(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no puede estar vacío"):
        sintetizar(
            " ",
            VozFalsa(),
            {"speaker_id": 0},
            tmp_path / "vacio.wav",
        )
