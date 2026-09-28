import asyncio
import json
import os
import re
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from clients.grabar_audio import grabar_audio
from voice.hablar import (
    cargar_voz,
    crear_configuracion,
    reproducir_wav,
    sintetizar,
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
    argumentos.add_argument("--segundos", type=float, default=6.0)
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

            print(
                f"Escuchando durante {opciones.segundos:g} segundos..."
            )
            informe, microfono, desbordamientos = await asyncio.to_thread(
                grabar_audio,
                opciones.segundos,
                RUTA_PREGUNTA,
                opciones.microfono,
            )
            print(f"Micrófono: {microfono}")
            if desbordamientos:
                print(
                    "Aviso: hubo "
                    f"{desbordamientos} desbordamiento(s) de audio."
                )
            if informe.rms < 50:
                print("No he oído voz suficiente. Inténtalo otra vez.")
                continue

            print("Transcribiendo...")
            transcripcion = await asyncio.to_thread(
                transcribir_audio,
                RUTA_PREGUNTA,
                modelo,
            )
            print(f"Jhony: {transcripcion.texto}")
            print("ASTRO: ", end="", flush=True)
            respuesta = await recibir_respuesta(
                websocket,
                transcripcion.texto,
                lambda fragmento: print(
                    fragmento,
                    end="",
                    flush=True,
                ),
            )
            print()
            print(
                f"[{respuesta.peticiones} petición/es | "
                f"{respuesta.tokens} tokens | "
                f"{respuesta.coste_usd:.6f} USD estimados]"
            )

            texto_hablado = limpiar_para_voz(respuesta.texto)
            await asyncio.to_thread(
                sintetizar,
                texto_hablado,
                voz,
                configuracion_voz,
                RUTA_RESPUESTA,
            )
            print("Reproduciendo la respuesta...")
            desbordado = await asyncio.to_thread(
                reproducir_wav,
                RUTA_RESPUESTA,
                opciones.altavoz,
            )
            if desbordado:
                print("Aviso: pudo producirse un corte al reproducir.")


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
