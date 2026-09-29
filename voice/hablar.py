from argparse import ArgumentParser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
import wave


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_VOZ = (
    RAIZ_PROYECTO
    / "data"
    / "models"
    / "piper"
    / "es_ES-sharvard-medium.onnx"
)
RUTA_SALIDA = RAIZ_PROYECTO / "data" / "audio" / "astro-respuesta.wav"
HABLANTES = {"M": 0, "F": 1}
TEXTO_PREDETERMINADO = (
    "Hola, Jhony. Soy ASTRO y ya puedo hablar sin conexión."
)


@dataclass(frozen=True)
class InformeSintesis:
    ruta: Path
    duracion_audio: float
    duracion_proceso: float
    frecuencia_hz: int
    canales: int
    bits_por_muestra: int


def cargar_voz(
    ruta: Path = RUTA_VOZ,
    cargador: Callable[..., Any] | None = None,
) -> Any:
    configuracion = Path(f"{ruta}.json")
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el modelo de voz: {ruta}")
    if not configuracion.is_file():
        raise FileNotFoundError(
            f"No existe la configuración de la voz: {configuracion}"
        )

    if cargador is None:
        try:
            from piper import PiperVoice
        except ImportError as error:
            raise RuntimeError(
                "Falta piper-tts. Instala requirements-voice.txt."
            ) from error
        cargador = PiperVoice.load

    return cargador(ruta, config_path=configuracion)


def crear_configuracion(
    hablante: str = "M",
    fabrica: Callable[..., Any] | None = None,
) -> Any:
    if hablante not in HABLANTES:
        raise ValueError(f"Hablante desconocido: {hablante}")

    if fabrica is None:
        from piper import SynthesisConfig

        fabrica = SynthesisConfig

    return fabrica(speaker_id=HABLANTES[hablante])


def inspeccionar_wav(
    ruta: Path,
    duracion_proceso: float,
) -> InformeSintesis:
    with wave.open(str(ruta), "rb") as archivo:
        if archivo.getcomptype() != "NONE":
            raise ValueError("El audio debe usar PCM sin compresión")
        frecuencia_hz = archivo.getframerate()
        canales = archivo.getnchannels()
        bits_por_muestra = archivo.getsampwidth() * 8
        muestras = archivo.getnframes()

    return InformeSintesis(
        ruta=ruta,
        duracion_audio=muestras / frecuencia_hz,
        duracion_proceso=duracion_proceso,
        frecuencia_hz=frecuencia_hz,
        canales=canales,
        bits_por_muestra=bits_por_muestra,
    )


def sintetizar(
    texto: str,
    voz: Any,
    configuracion: Any,
    salida: Path = RUTA_SALIDA,
    reloj: Callable[[], float] = perf_counter,
) -> InformeSintesis:
    texto = texto.strip()
    if not texto:
        raise ValueError("El texto no puede estar vacío")

    salida.parent.mkdir(parents=True, exist_ok=True)
    inicio = reloj()
    with wave.open(str(salida), "wb") as archivo:
        voz.synthesize_wav(
            texto,
            archivo,
            syn_config=configuracion,
        )
    duracion_proceso = reloj() - inicio
    return inspeccionar_wav(salida, duracion_proceso)


def cargar_sounddevice() -> Any:
    try:
        import sounddevice
    except ImportError as error:
        raise RuntimeError(
            "Falta sounddevice. Instala requirements-voice.txt."
        ) from error
    return sounddevice


def reproducir_wav(
    ruta: Path,
    dispositivo: int | None = None,
    modulo_audio: Any | None = None,
    detener: Any | None = None,
) -> bool:
    with wave.open(str(ruta), "rb") as archivo:
        if archivo.getsampwidth() != 2:
            raise ValueError("La reproducción requiere PCM de 16 bits")
        frecuencia_hz = archivo.getframerate()
        canales = archivo.getnchannels()
        datos = archivo.readframes(archivo.getnframes())

    audio = modulo_audio or cargar_sounddevice()
    with audio.RawOutputStream(
        samplerate=frecuencia_hz,
        device=dispositivo,
        channels=canales,
        dtype="int16",
    ) as flujo:
        if detener is None:
            desbordado = flujo.write(datos)
        else:
            desbordado = False
            tamano = max(2 * canales, int(frecuencia_hz * 0.02) * 2 * canales)
            for inicio in range(0, len(datos), tamano):
                if detener.is_set():
                    flujo.abort()
                    registrar = getattr(detener, "registrar_detencion", None)
                    if registrar is not None:
                        registrar()
                    break
                desbordado |= flujo.write(datos[inicio:inicio + tamano])
    return bool(desbordado)


def crear_argumentos() -> ArgumentParser:
    argumentos = ArgumentParser(
        description="Convierte texto en voz local mediante Piper.",
    )
    argumentos.add_argument(
        "texto",
        nargs="?",
        default=TEXTO_PREDETERMINADO,
    )
    argumentos.add_argument("--salida", type=Path, default=RUTA_SALIDA)
    argumentos.add_argument(
        "--hablante",
        choices=sorted(HABLANTES),
        default="M",
    )
    argumentos.add_argument("--dispositivo", type=int)
    argumentos.add_argument(
        "--sin-reproducir",
        action="store_true",
    )
    return argumentos


def main() -> int:
    opciones = crear_argumentos().parse_args()
    try:
        print("Cargando la voz local...")
        voz = cargar_voz()
        configuracion = crear_configuracion(opciones.hablante)
        informe = sintetizar(
            opciones.texto,
            voz,
            configuracion,
            opciones.salida,
        )
        print(f"Archivo: {informe.ruta.resolve()}")
        print(f"Audio: {informe.duracion_audio:.2f} s")
        print(f"Proceso: {informe.duracion_proceso:.2f} s")
        print(
            f"Formato: {informe.canales} canal(es), "
            f"{informe.bits_por_muestra} bits, "
            f"{informe.frecuencia_hz} Hz"
        )

        if not opciones.sin_reproducir:
            print("Reproduciendo...")
            desbordado = reproducir_wav(
                informe.ruta,
                opciones.dispositivo,
            )
            if desbordado:
                print("Aviso: se detectó un corte durante la reproducción")
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"No se pudo generar la voz: {error}")
        return 1
    except Exception as error:
        print(f"El sistema de voz falló: {type(error).__name__}: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
