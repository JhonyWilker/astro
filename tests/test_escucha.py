from pathlib import Path
from threading import Event
import wave

import numpy as np
import pytest

from voice.activacion import ConfiguracionActivacion, DetectorActivacion
from voice.escucha import ConfiguracionFrase, EscuchaContinua


class ModeloFalso:
    def __init__(self, puntuaciones):
        self.puntuaciones = iter(puntuaciones)

    def reset(self) -> None:
        return None

    def predict(self, bloque):
        return {"astro": next(self.puntuaciones, 0.0)}


class VadFalso:
    def reiniciar(self) -> None:
        return None

    def probabilidad(self, bloque) -> float:
        return 1.0 if np.abs(bloque).mean() > 1000 else 0.0


class FlujoFalso:
    def __init__(self, señal):
        self.señal = señal
        self.posicion = 0

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback) -> None:
        return None

    def read(self, cantidad):
        if self.posicion >= len(self.señal):
            raise EOFError("fin del audio simulado")
        trozo = self.señal[self.posicion:self.posicion + cantidad]
        self.posicion += cantidad
        if len(trozo) < cantidad:
            trozo = np.concatenate(
                (trozo, np.zeros(cantidad - len(trozo), dtype=np.int16))
            )
        return trozo.tobytes(), False


class AudioFalso:
    def __init__(self, señal):
        self.señal = señal
        self.opciones = None

    def RawInputStream(self, **opciones):
        self.opciones = opciones
        return FlujoFalso(self.señal)


def señal_con_frase(bloques_de_espera=3) -> np.ndarray:
    return np.concatenate(
        (
            np.full(1280 * bloques_de_espera, 3000, dtype=np.int16),
            np.full(8000, 3000, dtype=np.int16),
            np.zeros(16000, dtype=np.int16),
        )
    )


def crear_escucha(señal, puntuaciones, dispositivo=None):
    audio = AudioFalso(señal)
    detector = DetectorActivacion(
        ConfiguracionActivacion(),
        modelo=ModeloFalso(puntuaciones),
        vad=VadFalso(),
    )
    escucha = EscuchaContinua(
        detector,
        vad_frase=VadFalso(),
        dispositivo=dispositivo,
        modulo_audio=audio,
    )
    return escucha, audio


def configuracion_prueba() -> ConfiguracionFrase:
    return ConfiguracionFrase(
        espera_maxima=0.3,
        duracion_maxima=2.0,
        silencio_final=0.2,
    )


def test_espera_la_activacion_y_captura_la_frase(tmp_path: Path) -> None:
    escucha, audio = crear_escucha(señal_con_frase(), [0.0, 0.0, 0.9], 4)
    activaciones = []

    resultado = escucha.esperar_frase(
        tmp_path / "frase.wav",
        configuracion_prueba(),
        al_activar=activaciones.append,
    )

    assert audio.opciones == {
        "samplerate": 16000,
        "device": 4,
        "channels": 1,
        "dtype": "int16",
    }
    assert activaciones == [resultado.activacion]
    assert resultado.activacion.puntuacion == pytest.approx(0.9)
    assert resultado.informe.frecuencia_hz == 16000
    assert 0.9 <= resultado.informe.duracion_segundos <= 1.1
    assert resultado.desbordamientos == 0


def test_conserva_audio_oido_mientras_confirma_astro(tmp_path: Path) -> None:
    señal = np.concatenate(
        (
            np.full(1280, 1100, dtype=np.int16),
            np.full(1280, 2200, dtype=np.int16),
            np.full(1280, 3300, dtype=np.int16),
            np.full(4096, 4400, dtype=np.int16),
            np.zeros(16000, dtype=np.int16),
        )
    )
    escucha, _ = crear_escucha(señal, [0.0, 0.0, 0.9])
    salida = tmp_path / "frase-con-frontera.wav"

    resultado = escucha.esperar_frase(
        salida,
        configuracion_prueba(),
    )

    with wave.open(str(salida), "rb") as archivo:
        pcm = np.frombuffer(
            archivo.readframes(archivo.getnframes()),
            dtype=np.int16,
        )
    assert resultado.informe.duracion_segundos > 0.7
    assert 1100 in pcm
    assert 2200 in pcm
    assert 3300 in pcm
    assert 4400 in pcm


def test_no_captura_nada_hasta_que_se_activa(tmp_path: Path) -> None:
    escucha, _ = crear_escucha(señal_con_frase(), [0.0, 0.0, 0.0])

    with pytest.raises(EOFError):
        escucha.esperar_frase(tmp_path / "frase.wav", configuracion_prueba())

    assert not (tmp_path / "frase.wav").exists()


def test_rechaza_silencio_despues_de_activarse(tmp_path: Path) -> None:
    señal = np.concatenate(
        (
            np.full(1280 * 3, 3000, dtype=np.int16),
            np.zeros(32000, dtype=np.int16),
        )
    )
    escucha, _ = crear_escucha(señal, [0.0, 0.0, 0.9])

    salida = tmp_path / "frase.wav"
    with pytest.raises(ValueError, match="No se detectó voz"):
        escucha.esperar_frase(salida, configuracion_prueba())

    assert not salida.exists()


def test_se_puede_cancelar_la_espera(tmp_path: Path) -> None:
    escucha, _ = crear_escucha(señal_con_frase(), [0.0, 0.0, 0.9])
    cancelar = Event()
    cancelar.set()

    with pytest.raises(InterruptedError):
        escucha.esperar_frase(
            tmp_path / "frase.wav",
            configuracion_prueba(),
            cancelar=cancelar,
        )


def test_limita_la_duracion_maxima(tmp_path: Path) -> None:
    señal = np.full(1280 * 3 + 64000, 3000, dtype=np.int16)
    escucha, _ = crear_escucha(señal, [0.0, 0.0, 0.9])

    resultado = escucha.esperar_frase(
        tmp_path / "frase.wav",
        ConfiguracionFrase(
            espera_maxima=0.3,
            duracion_maxima=1.0,
            silencio_final=0.2,
        ),
    )

    assert resultado.informe.duracion_segundos == pytest.approx(1.24, abs=0.05)


def test_captura_un_seguimiento_sin_otra_activacion(tmp_path: Path) -> None:
    señal = np.concatenate(
        (
            np.full(8000, 3000, dtype=np.int16),
            np.zeros(16000, dtype=np.int16),
        )
    )
    escucha, _ = crear_escucha(señal, [])

    resultado = escucha.esperar_seguimiento(
        tmp_path / "seguimiento.wav",
        configuracion_prueba(),
    )

    assert resultado.informe.frecuencia_hz == 16000
    assert 0.6 <= resultado.informe.duracion_segundos <= 0.9
    assert resultado.desbordamientos == 0


def test_continua_una_interrupcion_sin_perder_su_inicio(tmp_path: Path) -> None:
    inicio = np.full(3200, 2500, dtype=np.int16).tobytes()
    escucha, _ = crear_escucha(np.zeros(16000, dtype=np.int16), [])
    salida = tmp_path / "interrupcion.wav"

    resultado = escucha.esperar_seguimiento(
        salida,
        configuracion_prueba(),
        audio_inicial=inicio,
        voz_inicial_confirmada=True,
    )

    with wave.open(str(salida), "rb") as archivo:
        pcm = np.frombuffer(
            archivo.readframes(archivo.getnframes()),
            dtype=np.int16,
        )
    assert resultado.informe.frecuencia_hz == 16000
    assert np.all(pcm[:3200] == 2500)


def test_seguimiento_sin_voz_caduca_y_no_guarda_audio(
    tmp_path: Path,
) -> None:
    escucha, _ = crear_escucha(np.zeros(16000, dtype=np.int16), [])
    salida = tmp_path / "seguimiento.wav"

    with pytest.raises(ValueError, match="No se detectó voz"):
        escucha.esperar_seguimiento(
            salida,
            configuracion_prueba(),
        )

    assert not salida.exists()


@pytest.mark.parametrize(
    "opciones",
    [
        {"espera_maxima": 0},
        {"duracion_maxima": 100},
        {"silencio_final": 0.1},
        {"umbral_voz": 2},
    ],
)
def test_rechaza_configuracion_de_frase_invalida(
    tmp_path: Path,
    opciones,
) -> None:
    escucha, _ = crear_escucha(señal_con_frase(), [])

    with pytest.raises(ValueError):
        escucha.esperar_frase(
            tmp_path / "frase.wav",
            ConfiguracionFrase(**opciones),
        )
