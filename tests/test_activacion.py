import json

import numpy as np
import pytest

from voice import activacion
from voice.activacion import (
    Activacion,
    ConfiguracionActivacion,
    DetectorActivacion,
    registrar_activacion,
)
from voice.vad_silero import VadSilero


BLOQUE = 1280


class ModeloFalso:
    def __init__(self, puntuaciones):
        self.puntuaciones = iter(puntuaciones)
        self.reinicios = 0

    def reset(self) -> None:
        self.reinicios += 1

    def predict(self, bloque):
        return {"astro": next(self.puntuaciones, 0.0)}


class VadFalso:
    def reiniciar(self) -> None:
        return None

    def probabilidad(self, bloque) -> float:
        return 1.0 if np.abs(bloque).mean() > 1000 else 0.0


def voz(bloques: int = 1) -> np.ndarray:
    return np.full(BLOQUE * bloques, 3000, dtype=np.int16)


def silencio(bloques: int = 1) -> np.ndarray:
    return np.zeros(BLOQUE * bloques, dtype=np.int16)


def crear_detector(puntuaciones, **opciones) -> DetectorActivacion:
    return DetectorActivacion(
        ConfiguracionActivacion(**opciones),
        modelo=ModeloFalso(puntuaciones),
        vad=VadFalso(),
    )


def test_activa_con_voz_y_puntuacion_alta() -> None:
    detector = crear_detector([0.0, 0.9])

    assert detector.alimentar(voz()) is None
    activacion = detector.alimentar(voz())

    assert activacion is not None
    assert activacion.modelo == "astro"
    assert activacion.puntuacion == pytest.approx(0.9)


def test_no_activa_si_no_hubo_voz() -> None:
    detector = crear_detector([0.9, 0.9, 0.9])

    for _ in range(3):
        assert detector.alimentar(silencio()) is None


def test_no_activa_si_la_voz_quedo_fuera_de_la_ventana() -> None:
    detector = crear_detector(
        [0.0] * 40 + [0.9],
        ventana_voz=0.5,
    )
    detector.alimentar(voz())
    for _ in range(39):
        assert detector.alimentar(silencio()) is None

    assert detector.alimentar(silencio()) is None


def test_periodo_de_descanso_evita_activaciones_repetidas() -> None:
    detector = crear_detector([0.9] * 30, refractario=2.0)

    primera = detector.alimentar(voz())
    repetidas = [detector.alimentar(voz()) for _ in range(20)]

    assert primera is not None
    assert all(resultado is None for resultado in repetidas)
    assert detector._modelo.reinicios >= 2


def test_activa_de_nuevo_al_terminar_el_descanso() -> None:
    detector = crear_detector([0.9] * 30, refractario=0.16)

    resultados = [detector.alimentar(voz()) is not None for _ in range(8)]

    assert resultados.count(True) >= 2


def test_exige_bloques_consecutivos() -> None:
    detector = crear_detector(
        [0.9, 0.0, 0.9, 0.9],
        bloques_consecutivos=2,
    )

    resultados = [detector.alimentar(voz()) for _ in range(4)]

    assert resultados[:3] == [None, None, None]
    assert resultados[3] is not None


def test_alimentar_acepta_bloques_de_cualquier_tamano() -> None:
    detector = crear_detector([0.0, 0.0, 0.9])
    audio = voz(3)

    resultados = [
        detector.alimentar(audio[i:i + 500])
        for i in range(0, len(audio), 500)
    ]

    assert sum(resultado is not None for resultado in resultados) == 1


def test_rechaza_audio_que_no_es_pcm16() -> None:
    detector = crear_detector([])

    with pytest.raises(ValueError, match="16 bits"):
        detector.alimentar(np.zeros(BLOQUE, dtype=np.float32))


@pytest.mark.parametrize(
    "opciones",
    [
        {"umbral": 0},
        {"umbral": 1.5},
        {"umbral_voz": 0},
        {"ventana_voz": 0.1},
        {"bloques_consecutivos": 0},
        {"refractario": -1},
    ],
)
def test_rechaza_configuracion_invalida(opciones) -> None:
    with pytest.raises(ValueError):
        crear_detector([], **opciones)


def test_registro_guarda_solo_fecha_modelo_y_puntuacion(tmp_path) -> None:
    ruta = tmp_path / "logs" / "activaciones.jsonl"

    registrar_activacion(Activacion(puntuacion=0.87654, modelo="astro"), ruta)
    registrar_activacion(Activacion(puntuacion=0.6, modelo="astro"), ruta)

    lineas = [json.loads(linea) for linea in ruta.read_text().splitlines()]
    assert len(lineas) == 2
    assert set(lineas[0]) == {"fecha", "modelo", "puntuacion"}
    assert lineas[0]["puntuacion"] == pytest.approx(0.8765)
    assert lineas[0]["fecha"].endswith("+00:00")


def test_guarda_la_puntuacion_maxima_oida_con_voz() -> None:
    detector = crear_detector([0.2, 0.4], umbral=0.9)

    detector.alimentar(voz())
    detector.alimentar(voz())

    assert detector.puntuacion_maxima_con_voz == pytest.approx(0.4)


def test_configuracion_usa_el_modelo_propio_y_sus_ajustes(tmp_path, monkeypatch) -> None:
    modelo = tmp_path / "astro.npz"
    modelo.write_bytes(b"")
    ajustes = tmp_path / "astro.json"
    ajustes.write_text('{"umbral": 0.93, "bloques_consecutivos": 3}')
    monkeypatch.setattr(activacion, "MODELO_ASTRO", modelo)
    monkeypatch.setattr(activacion, "AJUSTES_ASTRO", ajustes)

    configuracion = activacion.configuracion_predeterminada()

    assert configuracion.ruta_modelo == modelo
    assert configuracion.umbral == pytest.approx(0.93)
    assert configuracion.bloques_consecutivos == 3


def test_configuracion_falla_claro_si_falta_el_modelo_propio(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(activacion, "MODELO_ASTRO", tmp_path / "no_existe.npz")

    with pytest.raises(FileNotFoundError, match="Falta el modelo propio"):
        activacion.configuracion_predeterminada()


def test_configuracion_admite_un_modelo_elegido_expresamente(tmp_path) -> None:
    modelo = tmp_path / "modelo-elegido.onnx"

    configuracion = activacion.configuracion_predeterminada(modelo)

    assert configuracion.ruta_modelo == modelo


def test_ajustes_ausentes_usan_valores_prudentes(tmp_path, monkeypatch) -> None:
    modelo = tmp_path / "astro.npz"
    modelo.write_bytes(b"")
    monkeypatch.setattr(activacion, "MODELO_ASTRO", modelo)
    monkeypatch.setattr(activacion, "AJUSTES_ASTRO", tmp_path / "no_existe.json")

    configuracion = activacion.configuracion_predeterminada()

    assert configuracion.umbral == pytest.approx(0.9)
    assert configuracion.bloques_consecutivos == 2


class SesionONNXFalsa:
    def __init__(self):
        self.entradas = []

    def run(self, salidas, entradas):
        self.entradas.append(entradas)
        estado = np.ones((2, 1, 64), dtype=np.float32)
        return [np.array([[0.8]], dtype=np.float32), estado, estado]


def test_vad_devuelve_probabilidad_y_conserva_el_estado() -> None:
    sesion = SesionONNXFalsa()
    vad = VadSilero(sesion=sesion)
    bloque = np.zeros(512, dtype=np.int16)

    assert vad.probabilidad(bloque) == pytest.approx(0.8)
    vad.probabilidad(bloque)

    assert sesion.entradas[0]["h"].sum() == 0
    assert sesion.entradas[1]["h"].sum() == 2 * 64
    assert sesion.entradas[0]["input"].shape == (1, 512)
    assert int(sesion.entradas[0]["sr"]) == 16000

    vad.reiniciar()
    vad.probabilidad(bloque)
    assert sesion.entradas[2]["h"].sum() == 0


def test_vad_rechaza_bloques_de_otro_tamano() -> None:
    vad = VadSilero(sesion=SesionONNXFalsa())

    with pytest.raises(ValueError, match="512"):
        vad.probabilidad(np.zeros(100, dtype=np.int16))
