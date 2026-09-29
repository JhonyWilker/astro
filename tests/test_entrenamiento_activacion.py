import wave
from pathlib import Path

import numpy as np
import pytest

from voice.entrenar_activacion import (
    Aumentador,
    CHUNKS_CALENTAMIENTO,
    cargar_wav16,
    disparos,
    etiquetar,
    fin_de_habla,
)
from voice.modelo_astro import cargar_parametros, guardar_modelo, reenviar


class VadPorBloques:
    def __init__(self, con_voz: range):
        self.con_voz = con_voz
        self.indice = -1

    def reiniciar(self) -> None:
        self.indice = -1

    def probabilidad(self, bloque) -> float:
        self.indice += 1
        return 1.0 if self.indice in self.con_voz else 0.0


def test_etiquetar_marca_la_zona_positiva_y_descarta_la_ambigua() -> None:
    etiquetas = etiquetar(60, fin=2.0)

    positivas = np.flatnonzero(etiquetas == 1)
    assert 3 <= len(positivas) <= 4
    assert all(2.08 - 1e-6 <= (i + 1) * 0.08 <= 2.32 + 1e-6 for i in positivas)
    assert etiquetas[positivas[0] - 1] == -1
    assert etiquetas[positivas[-1] + 1] == -1
    assert (etiquetas[:CHUNKS_CALENTAMIENTO] == -1).all()
    assert etiquetas[-1] == 0


def test_sin_palabra_todo_es_negativo_salvo_el_calentamiento() -> None:
    etiquetas = etiquetar(30, fin=None)

    assert (etiquetas[:CHUNKS_CALENTAMIENTO] == -1).all()
    assert (etiquetas[CHUNKS_CALENTAMIENTO:] == 0).all()


def test_disparos_aplica_el_descanso() -> None:
    puntuaciones = np.zeros(100)
    puntuaciones[10:13] = 0.9
    puntuaciones[20] = 0.9
    puntuaciones[60] = 0.9

    assert disparos(puntuaciones, 0.5) == 2
    assert disparos(puntuaciones, 0.95) == 0


def test_fin_de_habla_devuelve_el_final_de_la_ultima_voz() -> None:
    audio = np.zeros(512 * 30, dtype=np.int16)

    fin = fin_de_habla(audio, VadPorBloques(range(10, 20)))

    assert fin == pytest.approx(20 * 512 / 16000)


def test_fin_de_habla_ignora_un_bloque_suelto() -> None:
    audio = np.zeros(512 * 30, dtype=np.int16)

    assert fin_de_habla(audio, VadPorBloques(range(5, 6))) is None


def test_red_calcula_la_probabilidad_esperada() -> None:
    capas = [(np.array([[2.0]]), np.array([-1.0]))]

    resultado = reenviar(capas, np.array([0.0]), np.array([1.0]), np.array([[0.5], [1.0]]))

    assert resultado == pytest.approx([0.5, 1 / (1 + np.exp(-1.0))])


def test_modelo_se_guarda_y_se_carga_igual(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    capas = [
        (rng.normal(size=(6, 4)).astype(np.float32), rng.normal(size=4).astype(np.float32)),
        (rng.normal(size=(4, 1)).astype(np.float32), rng.normal(size=1).astype(np.float32)),
    ]
    media = rng.normal(size=6).astype(np.float32)
    escala = (rng.random(6) + 0.5).astype(np.float32)
    ruta = tmp_path / "modelo.npz"
    filas = rng.normal(size=(5, 6)).astype(np.float32)

    guardar_modelo(ruta, capas, media, escala)
    cargadas, media2, escala2 = cargar_parametros(ruta)

    assert np.allclose(
        reenviar(capas, media, escala, filas),
        reenviar(cargadas, media2, escala2, filas),
    )
    assert len(cargadas) == 2


def test_aumentador_conserva_la_palabra_dentro_de_la_señal() -> None:
    aumentador = Aumentador(np.random.default_rng(3), [], [])
    clip = np.full(16000, 3000, dtype=np.int16)

    señal, fin = aumentador.componer(clip, fin_clip=0.9)

    assert señal.dtype == np.int16
    assert 1.7 <= fin <= 3.1
    assert len(señal) > fin * 16000


def test_aumentador_sin_aumento_conserva_la_duracion_del_clip() -> None:
    aumentador = Aumentador(np.random.default_rng(3), [], [])
    clip = np.full(16000, 3000, dtype=np.int16)

    señal, fin = aumentador.componer(clip, fin_clip=0.9, aumentar=False)

    assert 1.9 <= fin <= 2.9
    assert len(señal) >= 16000 + 2 * 16000 - 1


def test_aumentador_sin_palabra_no_devuelve_fin() -> None:
    aumentador = Aumentador(np.random.default_rng(3), [], [])

    señal, fin = aumentador.componer(
        np.zeros(8000, dtype=np.int16), None, con_pausas=False, aumentar=False
    )

    assert fin is None
    assert len(señal) == 8000 + 2 * 8000


def test_cargar_wav16_remuestrea_a_16_khz(tmp_path: Path) -> None:
    ruta = tmp_path / "prueba.wav"
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(22050)
        archivo.writeframes(np.zeros(22050, dtype=np.int16).tobytes())

    audio = cargar_wav16(ruta)

    assert audio.dtype == np.int16
    assert len(audio) == pytest.approx(16000, abs=2)
