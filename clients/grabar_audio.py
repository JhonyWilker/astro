from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from struct import iter_unpack
from typing import Any
import math
import wave


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_PREDETERMINADA = RAIZ_PROYECTO / "data" / "audio" / "prueba.wav"
CANALES = 1
BYTES_POR_MUESTRA = 2
FORMATO_MUESTRA = "int16"
BLOQUE_MUESTRAS = 1024


@dataclass(frozen=True)
class InformeAudio:
    ruta: Path
    duracion_segundos: float
    frecuencia_hz: int
    muestras: int
    pico: int
    rms: float


def cargar_sounddevice() -> Any:
    try:
        import sounddevice
    except ImportError as error:
        raise RuntimeError(
            "Falta sounddevice. Instala requirements-voice.txt."
        ) from error
    return sounddevice


def guardar_wav(ruta: Path, datos: bytes, frecuencia_hz: int) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(CANALES)
        archivo.setsampwidth(BYTES_POR_MUESTRA)
        archivo.setframerate(frecuencia_hz)
        archivo.writeframes(datos)


def analizar_wav(ruta: Path) -> InformeAudio:
    with wave.open(str(ruta), "rb") as archivo:
        if archivo.getnchannels() != CANALES:
            raise ValueError("El WAV debe ser mono")
        if archivo.getsampwidth() != BYTES_POR_MUESTRA:
            raise ValueError("El WAV debe usar PCM de 16 bits")
        frecuencia_hz = archivo.getframerate()
        muestras = archivo.getnframes()
        datos = archivo.readframes(muestras)

    valores = (muestra[0] for muestra in iter_unpack("<h", datos))
    pico = 0
    suma_cuadrados = 0
    cantidad = 0
    for valor in valores:
        pico = max(pico, abs(valor))
        suma_cuadrados += valor * valor
        cantidad += 1
    rms = math.sqrt(suma_cuadrados / cantidad) if cantidad else 0.0
    duracion = muestras / frecuencia_hz if frecuencia_hz else 0.0
    return InformeAudio(
        ruta=ruta,
        duracion_segundos=duracion,
        frecuencia_hz=frecuencia_hz,
        muestras=muestras,
        pico=pico,
        rms=rms,
    )


def grabar_audio(
    segundos: float,
    salida: Path = RUTA_PREDETERMINADA,
    dispositivo: int | None = None,
    modulo_audio: Any | None = None,
) -> tuple[InformeAudio, str, int]:
    if segundos <= 0 or segundos > 60:
        raise ValueError("La duración debe estar entre 0 y 60 segundos")

    audio = modulo_audio or cargar_sounddevice()
    informacion = audio.query_devices(dispositivo, "input")
    frecuencia_hz = round(float(informacion["default_samplerate"]))
    muestras_pendientes = round(frecuencia_hz * segundos)
    fragmentos: list[bytes] = []
    desbordamientos = 0

    with audio.RawInputStream(
        samplerate=frecuencia_hz,
        device=dispositivo,
        channels=CANALES,
        dtype=FORMATO_MUESTRA,
    ) as flujo:
        while muestras_pendientes:
            cantidad = min(BLOQUE_MUESTRAS, muestras_pendientes)
            datos, desbordado = flujo.read(cantidad)
            fragmentos.append(bytes(datos))
            desbordamientos += int(desbordado)
            muestras_pendientes -= cantidad

    guardar_wav(salida, b"".join(fragmentos), frecuencia_hz)
    return analizar_wav(salida), str(informacion["name"]), desbordamientos


def listar_dispositivos(modulo_audio: Any | None = None) -> None:
    audio = modulo_audio or cargar_sounddevice()
    predeterminado = audio.default.device[0]
    for indice, dispositivo in enumerate(audio.query_devices()):
        if dispositivo["max_input_channels"] <= 0:
            continue
        marca = " (predeterminado)" if indice == predeterminado else ""
        print(f"{indice}: {dispositivo['name']}{marca}")


def crear_argumentos() -> ArgumentParser:
    argumentos = ArgumentParser(
        description="Graba el micrófono en un archivo WAV local.",
    )
    argumentos.add_argument("--segundos", type=float, default=5.0)
    argumentos.add_argument("--salida", type=Path, default=RUTA_PREDETERMINADA)
    argumentos.add_argument("--dispositivo", type=int)
    argumentos.add_argument("--listar", action="store_true")
    return argumentos


def main() -> int:
    opciones = crear_argumentos().parse_args()
    try:
        if opciones.listar:
            listar_dispositivos()
            return 0
        print(f"Grabando {opciones.segundos:g} segundos. Habla ahora…")
        informe, microfono, desbordamientos = grabar_audio(
            opciones.segundos,
            opciones.salida,
            opciones.dispositivo,
        )
    except (RuntimeError, ValueError) as error:
        print(f"No se pudo grabar: {error}")
        return 1
    except Exception as error:
        print(f"El sistema de audio falló: {type(error).__name__}: {error}")
        return 1

    print(f"Micrófono: {microfono}")
    print(f"Archivo: {informe.ruta.resolve()}")
    print(f"Duración: {informe.duracion_segundos:.2f} s")
    print(f"Formato: mono · PCM 16 bits · {informe.frecuencia_hz} Hz")
    print(f"Nivel: RMS {informe.rms:.0f} · pico {informe.pico}")
    if desbordamientos:
        print(f"Aviso: se detectaron {desbordamientos} desbordamientos")
    if informe.rms < 50:
        print("Aviso: el audio parece contener silencio o un nivel muy bajo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
