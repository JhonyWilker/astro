from pathlib import Path
from struct import pack

import pytest

from voice.hablar import (
    crear_configuracion,
    reproducir_wav,
    sintetizar,
)


class VozFalsa:
    def synthesize_wav(self, texto, archivo, syn_config):
        assert texto == "Hola, Jhony."
        assert syn_config == {"speaker_id": 0}
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(22050)
        archivo.writeframes(pack("<h", 1000) * 2205)


class FlujoSalidaFalso:
    def __init__(self):
        self.datos = b""

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback) -> None:
        return None

    def write(self, datos: bytes) -> bool:
        self.datos = bytes(datos)
        return False


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


def test_sintetizar_rechaza_texto_vacio(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no puede estar vacío"):
        sintetizar(
            " ",
            VozFalsa(),
            {"speaker_id": 0},
            tmp_path / "vacio.wav",
        )
