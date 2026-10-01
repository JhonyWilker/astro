from collections import deque

import numpy as np
import pytest

from voice.eco import MUESTRAS_ECO
from voice.interrupcion import (
    ControlInterrupcion,
    DetectorInterrupcionEco,
    es_orden_silencio,
    transcripcion_interrupcion_fiable,
)
from voice.transcribir import ResultadoTranscripcion, SegmentoTranscrito
from voice.vad_silero import MUESTRAS_BLOQUE


class CanceladorFalso:
    def __init__(self, valor=7):
        self.valor = valor
        self.llamadas = []

    def procesar(self, microfono, referencia):
        self.llamadas.append((microfono.copy(), referencia.copy()))
        return np.full(MUESTRAS_ECO, self.valor, dtype=np.int16)


class VadFalso:
    def __init__(self, probabilidades):
        self.probabilidades = iter(probabilidades)
        self.bloques = []
        self.reinicios = 0

    def probabilidad(self, bloque):
        assert bloque.shape == (MUESTRAS_BLOQUE,)
        self.bloques.append(bloque.copy())
        return next(self.probabilidades)

    def reiniciar(self):
        self.reinicios += 1


def test_detector_confirma_tres_bloques_limpios_consecutivos() -> None:
    cancelador = CanceladorFalso()
    vad = VadFalso([0.9, 0.2, 0.9, 0.9, 0.9])
    detector = DetectorInterrupcionEco(cancelador, vad=vad)
    detectado = False

    for _ in range(40):
        detectado = detector.procesar(
            np.zeros(MUESTRAS_ECO, dtype=np.int16),
            np.ones(MUESTRAS_ECO, dtype=np.int16),
        )
        if detectado:
            break

    assert detectado is True
    assert len(vad.bloques) == 5
    assert detector.extraer_audio_interrupcion()
    assert len(detector.extraer_audio_interrupcion()) <= 30 * MUESTRAS_ECO * 2


@pytest.mark.parametrize(
    "texto",
    ["Shhhh", "Cállate ya.", "silencio", "Para", "deja de hablar"],
)
def test_reconoce_ordenes_locales_de_silencio(texto: str) -> None:
    assert es_orden_silencio(texto) is True


@pytest.mark.parametrize(
    "texto",
    ["Pero eso no es correcto", "Para qué sirve", "Espera, añade otra cosa"],
)
def test_una_interrupcion_con_contenido_no_es_orden_de_silencio(
    texto: str,
) -> None:
    assert es_orden_silencio(texto) is False


def _resultado_interrupcion(
    *,
    probabilidad_idioma: float = 0.99,
    probabilidad_silencio: float = 0.1,
    logprob_promedio: float = -0.2,
) -> ResultadoTranscripcion:
    return ResultadoTranscripcion(
        texto="Añade también la terraza",
        idioma="es",
        probabilidad_idioma=probabilidad_idioma,
        duracion_audio=0.8,
        duracion_proceso=0.1,
        segmentos=(
            SegmentoTranscrito(
                0.0,
                0.8,
                "Añade también la terraza",
                probabilidad_silencio,
                logprob_promedio,
            ),
        ),
    )


def test_acepta_una_interrupcion_transcrita_con_confianza() -> None:
    assert transcripcion_interrupcion_fiable(_resultado_interrupcion()) is True


@pytest.mark.parametrize(
    "opciones",
    [
        {"probabilidad_idioma": 0.2},
    ],
)
def test_rechaza_una_interrupcion_transcrita_sin_confianza(opciones) -> None:
    assert (
        transcripcion_interrupcion_fiable(_resultado_interrupcion(**opciones))
        is False
    )


def test_metricas_acusticas_de_whisper_no_rechazan_voz_confirmada() -> None:
    resultado = _resultado_interrupcion(
        probabilidad_silencio=0.8,
        logprob_promedio=-1.5,
    )

    assert transcripcion_interrupcion_fiable(resultado) is True


def test_detector_reinicia_solo_el_turno_no_el_cancelador() -> None:
    cancelador = CanceladorFalso()
    vad = VadFalso([0.9])
    detector = DetectorInterrupcionEco(cancelador, vad=vad)

    detector.preparar_fragmento()

    assert vad.reinicios == 1
    assert not hasattr(cancelador, "reiniciar")


def test_control_mide_desde_deteccion_hasta_detencion() -> None:
    tiempos = deque([10.0, 10.12])
    control = ControlInterrupcion(reloj=tiempos.popleft)

    assert control.detectar() is True
    assert control.detectar() is False
    control.registrar_detencion()

    assert control.latencia_segundos == pytest.approx(0.12)
