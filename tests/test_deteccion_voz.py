from pathlib import Path
from struct import pack

import pytest

from voice.detectar_voz import (
    ConfiguracionDeteccion,
    grabar_hasta_silencio,
    nivel_rms_pcm16,
)


class FlujoVADFalso:
    def __init__(self, niveles):
        self.niveles = iter(niveles)

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback) -> None:
        return None

    def read(self, cantidad):
        nivel = next(self.niveles, 0)
        return pack("<h", nivel) * cantidad, False


class AudioVADFalso:
    def __init__(self, niveles):
        self.flujo = FlujoVADFalso(niveles)

    def query_devices(self, dispositivo=None, tipo=None):
        return {
            "name": "Micrófono VAD",
            "default_samplerate": 8000,
        }

    def RawInputStream(self, **opciones):
        assert opciones == {
            "samplerate": 8000,
            "device": None,
            "channels": 1,
            "dtype": "int16",
        }
        return self.flujo


def configuracion_prueba() -> ConfiguracionDeteccion:
    return ConfiguracionDeteccion(
        espera_maxima=0.3,
        duracion_maxima=2.0,
        silencio_final=0.2,
        pregrabacion=0.15,
    )


def test_nivel_rms_pcm16_mide_la_energia() -> None:
    datos = pack("<hhhh", 1000, -1000, 1000, -1000)

    assert nivel_rms_pcm16(datos) == pytest.approx(1000)


def test_grabacion_detecta_inicio_y_silencio_final(
    tmp_path: Path,
) -> None:
    niveles = [20] * 5 + [1000] * 8 + [20] * 7
    salida = tmp_path / "frase.wav"

    informe, microfono, desbordamientos = grabar_hasta_silencio(
        salida,
        configuracion=configuracion_prueba(),
        modulo_audio=AudioVADFalso(niveles),
    )

    assert salida.exists()
    assert microfono == "Micrófono VAD"
    assert desbordamientos == 0
    assert informe.duracion_segundos == pytest.approx(0.51)
    assert informe.rms > 500


def test_grabacion_tolera_una_pausa_breve(
    tmp_path: Path,
) -> None:
    niveles = (
        [20] * 3
        + [1000] * 5
        + [20] * 3
        + [1000] * 5
        + [20] * 7
    )

    informe, _, _ = grabar_hasta_silencio(
        tmp_path / "pausa.wav",
        configuracion=configuracion_prueba(),
        modulo_audio=AudioVADFalso(niveles),
    )

    assert informe.duracion_segundos >= 0.6


def test_grabacion_rechaza_silencio_continuo(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="No se detectó voz"):
        grabar_hasta_silencio(
            tmp_path / "silencio.wav",
            configuracion=configuracion_prueba(),
            modulo_audio=AudioVADFalso([20] * 20),
        )
