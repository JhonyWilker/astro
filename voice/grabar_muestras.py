"""Graba las muestras de tu voz para entrenar la palabra de activación.

ASTRO te da las instrucciones hablando por los altavoces: solo hay que
escuchar y hablar después de cada pitido. Los audios quedan en
data/wakeword/muestras y nunca se suben a Git.
"""

import time
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from clients.grabar_audio import (
    CANALES,
    FORMATO_MUESTRA,
    cargar_sounddevice,
    guardar_wav,
)
from voice.activacion import FRECUENCIA_HZ
from voice.hablar import (
    cargar_voz,
    crear_configuracion,
    reproducir_wav,
    sintetizar,
)
from voice.vad_silero import RAIZ_PROYECTO


CARPETA_MUESTRAS = RAIZ_PROYECTO / "data" / "wakeword" / "muestras"
PAUSA_TRAS_PITIDO = 0.25
PAUSA_ENTRE_MUESTRAS = 0.6

PALABRAS_PARECIDAS = (
    "rastro",
    "astronauta",
    "hasta",
    "castro",
    "astuto",
    "astral",
    "cuatro",
    "asno",
    "astilla",
    "atrás",
    "ahora",
    "estrella",
)


@dataclass(frozen=True)
class Bloque:
    carpeta: str
    introduccion: str
    repeticiones: int
    segundos: float
    palabras: tuple[str, ...] = ()


BLOQUES = (
    Bloque(
        "positivas/normal",
        "Primer bloque. Cada vez que oigas el pitido, di Astro con voz "
        "normal, como si me llamaras desde el sofá.",
        25,
        2.0,
    ),
    Bloque(
        "positivas/lejos",
        "Segundo bloque. Ahora aléjate del ordenador, a un par de metros, "
        "y di Astro un poco más alto después de cada pitido.",
        12,
        2.0,
    ),
    Bloque(
        "positivas/bajo",
        "Tercer bloque. Acércate otra vez y di Astro en voz baja, casi "
        "susurrando.",
        8,
        2.0,
    ),
    Bloque(
        "positivas/frase",
        "Cuarto bloque. Después del pitido di Astro y sigue con cualquier "
        "pregunta, por ejemplo: Astro, qué hora es.",
        10,
        4.5,
    ),
    Bloque(
        "negativas/libre_1",
        "Quinto bloque. Después del pitido, habla durante un minuto de lo "
        "que quieras, por ejemplo qué has hecho hoy. No digas Astro.",
        1,
        60.0,
    ),
    Bloque(
        "negativas/libre_2",
        "Sexto bloque. Otro minuto. Cuéntame cómo va el restaurante o lee "
        "en voz alta lo que tengas en pantalla. Sin decir Astro.",
        1,
        60.0,
    ),
    Bloque(
        "negativas/parecidas",
        "Séptimo bloque. Yo digo una palabra, tú la repites después del "
        "pitido.",
        1,
        2.0,
        PALABRAS_PARECIDAS,
    ),
    Bloque(
        "negativas/silencio",
        "Último bloque. Quédate en silencio veinte segundos después del "
        "pitido.",
        1,
        20.0,
    ),
)


PALABRAS_CONFUSAS = (
    "astronauta", "castro", "rastro", "astronomía", "desastre", "catástrofe",
    "astros", "astral", "astuto", "hasta", "astilla", "rastrillo",
    "estrella", "Castro", "astrólogo",
)
FRASES_CONFUSAS = (
    "El astronauta salió de la nave.",
    "Vamos a casa de Castro.",
    "Sigue el rastro del perro.",
    "Qué desastre de día.",
    "Me gusta la astronomía.",
    "Hasta luego, nos vemos mañana.",
    "Ha sido una catástrofe.",
    "Los astros están alineados.",
)

BLOQUES_CONFUSAS = (
    Bloque(
        "negativas_extra/palabras",
        "Vamos a grabar palabras que se parecen a mi nombre. Yo digo una "
        "palabra y tú la repites después del pitido, con naturalidad.",
        1,
        2.0,
        PALABRAS_CONFUSAS * 3,
    ),
    Bloque(
        "negativas_extra/frases",
        "Ahora frases. Yo digo una frase y tú la repites entera después "
        "del pitido.",
        1,
        4.5,
        FRASES_CONFUSAS * 2,
    ),
)


def crear_pitido(
    frecuencia_tono: float = 880.0,
    segundos: float = 0.15,
) -> bytes:
    instantes = np.arange(int(FRECUENCIA_HZ * segundos)) / FRECUENCIA_HZ
    onda = 0.4 * np.sin(2 * np.pi * frecuencia_tono * instantes)
    return (onda * 32767).astype(np.int16).tobytes()


class Sesion:
    def __init__(
        self,
        audio: Any,
        voz: Any,
        configuracion_voz: Any,
        microfono: int | None,
        altavoz: int | None,
        carpeta: Path,
        esperar=time.sleep,
    ) -> None:
        self._audio = audio
        self._voz = voz
        self._configuracion_voz = configuracion_voz
        self._microfono = microfono
        self._altavoz = altavoz
        self._carpeta = carpeta
        self._esperar = esperar
        self._tmp = carpeta / "_locucion.wav"

    def decir(self, texto: str) -> None:
        print(f"ASTRO: {texto}", flush=True)
        sintetizar(texto, self._voz, self._configuracion_voz, self._tmp)
        reproducir_wav(self._tmp, self._altavoz, self._audio)

    def pitido(self) -> None:
        with self._audio.RawOutputStream(
            samplerate=FRECUENCIA_HZ,
            device=self._altavoz,
            channels=CANALES,
            dtype=FORMATO_MUESTRA,
        ) as flujo:
            flujo.write(crear_pitido())
        self._esperar(PAUSA_TRAS_PITIDO)

    def grabar(self, segundos: float, ruta: Path) -> None:
        cantidad = round(FRECUENCIA_HZ * segundos)
        with self._audio.RawInputStream(
            samplerate=FRECUENCIA_HZ,
            device=self._microfono,
            channels=CANALES,
            dtype=FORMATO_MUESTRA,
        ) as flujo:
            datos, _ = flujo.read(cantidad)
        guardar_wav(ruta, bytes(datos), FRECUENCIA_HZ)

    def ejecutar(self, bloques: tuple[Bloque, ...] = BLOQUES) -> int:
        grabadas = 0
        self.decir(
            "Vamos a grabar unas muestras de tu voz. Hablaré yo y tú solo "
            "tienes que hablar después de cada pitido. Empezamos."
        )
        for bloque in bloques:
            destino = self._carpeta / bloque.carpeta
            destino.mkdir(parents=True, exist_ok=True)
            self.decir(bloque.introduccion)
            self._esperar(1.0)
            total = len(bloque.palabras) or bloque.repeticiones
            for indice in range(total):
                if bloque.palabras:
                    self.decir(bloque.palabras[indice])
                self.pitido()
                ruta = destino / f"{bloque.carpeta.split('/')[-1]}_{indice + 1:03d}.wav"
                self.grabar(bloque.segundos, ruta)
                grabadas += 1
                print(
                    f"  {bloque.carpeta} {indice + 1}/{total}",
                    flush=True,
                )
                self._esperar(PAUSA_ENTRE_MUESTRAS)
        self.decir("Hemos terminado. Gracias, Jhony.")
        return grabadas


def crear_argumentos() -> ArgumentParser:
    argumentos = ArgumentParser(
        description="Graba las muestras de voz para la palabra Astro.",
    )
    argumentos.add_argument("--microfono", type=int)
    argumentos.add_argument("--altavoz", type=int)
    argumentos.add_argument("--carpeta", type=Path, default=CARPETA_MUESTRAS)
    argumentos.add_argument(
        "--conjunto",
        choices=("principal", "confusas"),
        default="principal",
        help="«confusas» graba palabras y frases parecidas a Astro (astronauta, castro...).",
    )
    return argumentos


def main() -> int:
    opciones = crear_argumentos().parse_args()
    try:
        voz = cargar_voz()
        sesion = Sesion(
            cargar_sounddevice(),
            voz,
            crear_configuracion("M"),
            opciones.microfono,
            opciones.altavoz,
            opciones.carpeta,
        )
        opciones.carpeta.mkdir(parents=True, exist_ok=True)
        grabadas = sesion.ejecutar(
            BLOQUES_CONFUSAS if opciones.conjunto == "confusas" else BLOQUES
        )
    except KeyboardInterrupt:
        print("\nGrabación cancelada. Lo ya grabado se conserva.")
        return 1
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"No se pudo grabar: {error}")
        return 1
    print(f"Muestras grabadas: {grabadas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
