import asyncio
import json
import os
import re
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from voice.hablar import (
    cargar_voz,
    crear_configuracion,
)
from voice.streaming import SegmentadorTexto, reproducir_cola_streaming
from voice.detectar_voz import (
    ConfiguracionDeteccion,
    grabar_hasta_silencio,
)
from voice.transcribir import (
    MODELO_PREDETERMINADO,
    cargar_modelo,
    transcribir_audio,
)


RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
URL_PREDETERMINADA = "ws://astro-vps:8000/ws"
RUTA_PREGUNTA = RAIZ_PROYECTO / "data" / "audio" / "pregunta-voz.wav"
RUTA_RESPUESTA = RAIZ_PROYECTO / "data" / "audio" / "respuesta-voz.wav"


@dataclass(frozen=True)
class RespuestaRemota:
    texto: str
    peticiones: int
    tokens: int
    coste_usd: float


def limpiar_para_voz(texto: str) -> str:
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    texto = re.sub(r"[`*_#]", "", texto)
    return " ".join(texto.split())


async def recibir_respuesta(
    websocket: Any,
    texto: str,
    mostrar_fragmento: Callable[[str], None] | None = None,
) -> RespuestaRemota:
    await websocket.send(
        json.dumps(
            {"type": "message", "text": texto},
            ensure_ascii=False,
        )
    )
    fragmentos: list[str] = []

    while True:
        evento = json.loads(await websocket.recv())
        tipo = evento.get("type")

        if tipo == "delta":
            fragmento = str(evento.get("text", ""))
            fragmentos.append(fragmento)
            if mostrar_fragmento is not None:
                mostrar_fragmento(fragmento)
        elif tipo == "done":
            uso = evento.get("usage", [])
            respuesta = "".join(fragmentos).strip()
            if not respuesta:
                raise RuntimeError("ASTRO terminó sin enviar una respuesta")
            return RespuestaRemota(
                texto=respuesta,
                peticiones=len(uso),
                tokens=sum(int(item["tokens"]) for item in uso),
                coste_usd=sum(
                    float(item["coste_estimado_usd"])
                    for item in uso
                ),
            )
        elif tipo == "error":
            raise RuntimeError(
                str(evento.get("message", "ASTRO devolvió un error"))
            )


def crear_argumentos() -> ArgumentParser:
    argumentos = ArgumentParser(
        description="Conversación de voz manual con ASTRO.",
    )
    argumentos.add_argument(
        "--espera-maxima",
        type=float,
        default=5.0,
    )
    argumentos.add_argument(
        "--duracion-maxima",
        type=float,
        default=30.0,
    )
    argumentos.add_argument(
        "--silencio-final",
        type=float,
        default=1.0,
    )
    argumentos.add_argument("--microfono", type=int)
    argumentos.add_argument("--altavoz", type=int)
    argumentos.add_argument(
        "--modelo",
        default=MODELO_PREDETERMINADO,
    )
    argumentos.add_argument(
        "--hablante",
        choices=["M", "F"],
        default="M",
    )
    return argumentos


async def conversar(opciones: Any) -> None:
    url = os.getenv("ASTRO_WS_URL", URL_PREDETERMINADA)
    configuracion_deteccion = ConfiguracionDeteccion(
        espera_maxima=opciones.espera_maxima,
        duracion_maxima=opciones.duracion_maxima,
        silencio_final=opciones.silencio_final,
    )

    print(f"Cargando Whisper {opciones.modelo} en CPU...")
    modelo = await asyncio.to_thread(cargar_modelo, opciones.modelo)
    print("Cargando la voz local de ASTRO...")
    voz = await asyncio.to_thread(cargar_voz)
    configuracion_voz = crear_configuracion(opciones.hablante)

    print(f"Conectando con ASTRO en {url}...")
    async with websockets.connect(url) as websocket:
        listo = json.loads(await websocket.recv())
        if listo.get("type") != "ready":
            raise RuntimeError("ASTRO no confirmó la conexión")

        print("ASTRO conectado.")
        print("Pulsa Enter para hablar o escribe 'salir' para terminar.")

        while True:
            orden = (
                await asyncio.to_thread(input, "\n[Enter] Hablar: ")
            ).strip()
            if orden.lower() == "salir":
                print("Hasta luego, Jhony.")
                return
            if orden:
                print("Pulsa solo Enter para iniciar una grabación.")
                continue

            print("Escuchando... Habla ahora.")
            try:
                informe, microfono, desbordamientos = (
                    await asyncio.to_thread(
                        grabar_hasta_silencio,
                        RUTA_PREGUNTA,
                        opciones.microfono,
                        configuracion_deteccion,
                    )
                )
            except ValueError as error:
                print(f"No se pudo obtener una frase: {error}")
                continue

            print(
                f"Micrófono: {microfono} · "
                f"{informe.duracion_segundos:.2f} s"
            )
            if desbordamientos:
                print(
                    "Aviso: hubo "
                    f"{desbordamientos} desbordamiento(s) de audio."
                )
            inicio_respuesta = perf_counter()
            print("Transcribiendo...")
            transcripcion = await asyncio.to_thread(
                transcribir_audio,
                RUTA_PREGUNTA,
                modelo,
            )
            tiempo_transcripcion = perf_counter() - inicio_respuesta
            tiempo_primer_texto: float | None = None
            tiempo_primer_fragmento: float | None = None
            print(f"Jhony: {transcripcion.texto}")
            print("ASTRO: ", end="", flush=True)

            cola_texto: asyncio.Queue[str | None] = asyncio.Queue()
            segmentador = SegmentadorTexto()
            tarea_voz = asyncio.create_task(
                reproducir_cola_streaming(
                    cola_texto,
                    voz,
                    configuracion_voz,
                    opciones.altavoz,
                    RUTA_RESPUESTA,
                    inicio_respuesta,
                )
            )

            def mostrar_y_preparar(fragmento: str) -> None:
                nonlocal tiempo_primer_texto, tiempo_primer_fragmento
                ahora = perf_counter()
                if tiempo_primer_texto is None:
                    tiempo_primer_texto = ahora - inicio_respuesta
                print(fragmento, end="", flush=True)
                partes = segmentador.agregar(fragmento)
                if partes and tiempo_primer_fragmento is None:
                    tiempo_primer_fragmento = ahora - inicio_respuesta
                for parte in partes:
                    texto_hablado = limpiar_para_voz(parte)
                    if texto_hablado:
                        cola_texto.put_nowait(texto_hablado)

            try:
                respuesta = await recibir_respuesta(
                    websocket,
                    transcripcion.texto,
                    mostrar_y_preparar,
                )
            except BaseException:
                await cola_texto.put(None)
                await tarea_voz
                raise

            for parte in segmentador.finalizar():
                texto_hablado = limpiar_para_voz(parte)
                if texto_hablado:
                    await cola_texto.put(texto_hablado)
            await cola_texto.put(None)
            resultado_voz = await tarea_voz
            if (
                tiempo_primer_texto is None
                or tiempo_primer_fragmento is None
            ):
                raise RuntimeError(
                    "No se pudo medir el streaming de la respuesta"
                )

            print()
            print(
                f"[{respuesta.peticiones} petición/es | "
                f"{respuesta.tokens} tokens | "
                f"{respuesta.coste_usd:.6f} USD estimados]"
            )
            print(
                "Latencia acumulada: "
                f"STT {tiempo_transcripcion:.2f} s · "
                f"primer texto {tiempo_primer_texto:.2f} s · "
                f"primer fragmento {tiempo_primer_fragmento:.2f} s · "
                f"primera voz "
                f"{resultado_voz.latencia_primera_voz:.2f} s"
            )
            print(f"Voz: {resultado_voz.fragmentos} fragmento(s)")
            if resultado_voz.cortes_reproduccion:
                print(
                    "Aviso: pudo producirse un corte en "
                    f"{resultado_voz.cortes_reproduccion} fragmento(s)."
                )


def main() -> int:
    opciones = crear_argumentos().parse_args()
    try:
        asyncio.run(conversar(opciones))
    except KeyboardInterrupt:
        print("\nConversación terminada.")
    except (
        ConnectionClosed,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"No se pudo completar la conversación: {error}")
        return 1
    except Exception as error:
        print(
            "El cliente de voz falló: "
            f"{type(error).__name__}: {error}"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
