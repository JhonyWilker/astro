from pathlib import Path
from struct import pack

import pytest

from clients.grabar_audio import analizar_wav, grabar_audio


class FlujoFalso:
    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback) -> None:
        return None

    def read(self, cantidad: int) -> tuple[bytes, bool]:
        muestras = (1000 if indice % 2 == 0 else -1000 for indice in range(cantidad))
        return b"".join(pack("<h", muestra) for muestra in muestras), False


class AudioFalso:
    def query_devices(self, dispositivo=None, tipo=None):
        return {
            "name": "Micrófono de prueba",
            "default_samplerate": 8000,
        }

    def RawInputStream(self, **opciones):
        assert opciones == {
            "samplerate": 8000,
            "device": None,
            "channels": 1,
            "dtype": "int16",
        }
        return FlujoFalso()


def test_grabar_audio_crea_wav_mono_pcm16(tmp_path: Path) -> None:
    salida = tmp_path / "prueba.wav"

    informe, microfono, desbordamientos = grabar_audio(
        0.25,
        salida,
        modulo_audio=AudioFalso(),
    )

    assert salida.exists()
    assert informe == analizar_wav(salida)
    assert informe.duracion_segundos == pytest.approx(0.25)
    assert informe.frecuencia_hz == 8000
    assert informe.muestras == 2000
    assert informe.pico == 1000
    assert informe.rms == pytest.approx(1000)
    assert microfono == "Micrófono de prueba"
    assert desbordamientos == 0


@pytest.mark.parametrize("segundos", [0, -1, 61])
def test_grabar_audio_rechaza_duracion_invalida(
    segundos: float,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="entre 0 y 60"):
        grabar_audio(
            segundos,
            tmp_path / "invalido.wav",
            modulo_audio=AudioFalso(),
        )
