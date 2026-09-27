from argparse import ArgumentParser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_MODELOS = RAIZ_PROYECTO / "data" / "models" / "faster-whisper"
MODELO_PREDETERMINADO = "base"


@dataclass(frozen=True)
class SegmentoTranscrito:
    inicio: float
    fin: float
    texto: str


@dataclass(frozen=True)
class ResultadoTranscripcion:
    texto: str
    idioma: str
    probabilidad_idioma: float
    duracion_audio: float
    duracion_proceso: float
    segmentos: tuple[SegmentoTranscrito, ...]


def cargar_modelo(
    nombre: str = MODELO_PREDETERMINADO,
    fabrica: Callable[..., Any] | None = None,
) -> Any:
    if fabrica is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "Falta faster-whisper. Instala requirements-voice.txt."
            ) from error
        fabrica = WhisperModel

    return fabrica(
        nombre,
        device="cpu",
        compute_type="int8",
        download_root=str(RUTA_MODELOS),
    )


def transcribir_audio(
    ruta: Path,
    modelo: Any,
    reloj: Callable[[], float] = perf_counter,
) -> ResultadoTranscripcion:
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el audio: {ruta}")

    inicio = reloj()
    segmentos_crudos, informacion = modelo.transcribe(
        str(ruta),
        language="es",
        beam_size=5,
    )
    segmentos = tuple(
        SegmentoTranscrito(
            inicio=float(segmento.start),
            fin=float(segmento.end),
            texto=segmento.text.strip(),
        )
        for segmento in segmentos_crudos
        if segmento.text.strip()
    )
    duracion_proceso = reloj() - inicio
    texto = " ".join(segmento.texto for segmento in segmentos).strip()
    if not texto:
        raise ValueError("No se detectó voz en el audio")

    return ResultadoTranscripcion(
        texto=texto,
        idioma=str(informacion.language),
        probabilidad_idioma=float(informacion.language_probability),
        duracion_audio=float(informacion.duration),
        duracion_proceso=duracion_proceso,
        segmentos=segmentos,
    )


def formatear_segmento(segmento: SegmentoTranscrito) -> str:
    return (
        f"[{segmento.inicio:.2f} s -> {segmento.fin:.2f} s] "
        f"{segmento.texto}"
    )


def crear_argumentos() -> ArgumentParser:
    argumentos = ArgumentParser(
        description="Transcribe un archivo de audio local al español.",
    )
    argumentos.add_argument("audio", type=Path)
    argumentos.add_argument(
        "--modelo",
        default=MODELO_PREDETERMINADO,
        help="Modelo de faster-whisper que se cargará.",
    )
    return argumentos


def main() -> int:
    opciones = crear_argumentos().parse_args()
    try:
        print(f"Cargando el modelo {opciones.modelo} en CPU…")
        modelo = cargar_modelo(opciones.modelo)
        resultado = transcribir_audio(opciones.audio, modelo)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"No se pudo transcribir: {error}")
        return 1
    except Exception as error:
        print(f"El sistema de voz falló: {type(error).__name__}: {error}")
        return 1

    for segmento in resultado.segmentos:
        print(formatear_segmento(segmento))
    print(f"Texto: {resultado.texto}")
    print(
        f"Idioma: {resultado.idioma} "
        f"({resultado.probabilidad_idioma:.1%})"
    )
    print(f"Audio: {resultado.duracion_audio:.2f} s")
    print(f"Proceso: {resultado.duracion_proceso:.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
