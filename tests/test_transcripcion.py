from pathlib import Path
from types import SimpleNamespace

import pytest

from voice.transcribir import (
    SegmentoTranscrito,
    cargar_modelo,
    formatear_segmento,
    transcribir_audio,
)


class ModeloFalso:
    def transcribe(self, ruta: str, **opciones):
        assert Path(ruta).name == "voz.wav"
        assert opciones == {
            "language": "es",
            "beam_size": 5,
        }
        segmentos = iter(
            [
                SimpleNamespace(
                    start=0.0,
                    end=1.2,
                    text=" Hola ",
                    no_speech_prob=0.1,
                    avg_logprob=-0.2,
                ),
                SimpleNamespace(
                    start=1.2,
                    end=2.4,
                    text="Jhony.",
                    no_speech_prob=0.2,
                    avg_logprob=-0.3,
                ),
            ]
        )
        informacion = SimpleNamespace(
            language="es",
            language_probability=0.99,
            duration=2.4,
        )
        return segmentos, informacion


def test_transcribir_audio_reune_segmentos(tmp_path: Path) -> None:
    audio = tmp_path / "voz.wav"
    audio.write_bytes(b"audio simulado")
    tiempos = iter([10.0, 10.5])

    resultado = transcribir_audio(
        audio,
        ModeloFalso(),
        reloj=lambda: next(tiempos),
    )

    assert resultado.texto == "Hola Jhony."
    assert resultado.idioma == "es"
    assert resultado.probabilidad_idioma == pytest.approx(0.99)
    assert resultado.duracion_audio == pytest.approx(2.4)
    assert resultado.duracion_proceso == pytest.approx(0.5)
    assert len(resultado.segmentos) == 2
    assert resultado.segmentos[0].probabilidad_silencio == pytest.approx(0.1)
    assert resultado.segmentos[0].logprob_promedio == pytest.approx(-0.2)


def test_transcribir_audio_rechaza_archivo_inexistente(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="No existe el audio"):
        transcribir_audio(tmp_path / "ausente.wav", ModeloFalso())


def test_cargar_modelo_configura_cpu_int8() -> None:
    llamadas = []

    def fabrica(nombre, **opciones):
        llamadas.append((nombre, opciones))
        return object()

    cargar_modelo("base", fabrica=fabrica)

    assert llamadas == [
        (
            "base",
            {
                "device": "cpu",
                "compute_type": "int8",
                "download_root": str(
                    Path(__file__).resolve().parents[1]
                    / "data"
                    / "models"
                    / "faster-whisper"
                ),
            },
        )
    ]


def test_cargar_modelo_configura_cuda_int8_float16() -> None:
    llamadas = []

    def fabrica(nombre, **opciones):
        llamadas.append((nombre, opciones))
        return object()

    cargar_modelo("base", fabrica=fabrica, dispositivo="cuda")

    assert llamadas[0][1]["device"] == "cuda"
    assert llamadas[0][1]["compute_type"] == "int8_float16"


def test_formatear_segmento_es_compatible_con_consola() -> None:
    segmento = SegmentoTranscrito(0.0, 1.25, "Hola, Jhony.")

    texto = formatear_segmento(segmento)

    assert texto == "[0.00 s -> 1.25 s] Hola, Jhony."
    texto.encode("cp1252")
