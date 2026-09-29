import asyncio
import json
import os
import re
from argparse import ArgumentParser
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from threading import Event
from typing import Any, Callable

import websockets
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed

from voice.activacion import (
    Activacion,
    DetectorActivacion,
    configuracion_predeterminada,
    registrar_activacion,
)
from voice.escucha import ConfiguracionFrase, EscuchaContinua
from voice.hablar import (
    cargar_voz,
    crear_configuracion,
)
from voice.streaming import SegmentadorTexto, reproducir_cola_streaming
from voice.interrupcion import escuchar_interrupcion
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
        elif tipo == "cancelled":
            raise InterruptedError("Respuesta interrumpida")
        elif tipo == "busy":
            raise RuntimeError("Hay otro turno activo en esta conversación")


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
    argumentos.add_argument(
        "--activacion",
        action="store_true",
        help="Esperar la palabra de activación en vez de pulsar Enter.",
    )
    argumentos.add_argument("--modelo-activacion", type=Path)
    argumentos.add_argument("--umbral-activacion", type=float)
    argumentos.add_argument("--bloques-activacion", type=int)
    argumentos.add_argument("--altavoz", type=int)
    argumentos.add_argument("--interrumpir-con-voz", action="store_true",
                            help="Escuchar mientras responde; usar auriculares para evitar autoactivaciones.")
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
    load_dotenv(RAIZ_PROYECTO / ".env")
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

    escucha = None
    configuracion_frase = ConfiguracionFrase(
        espera_maxima=opciones.espera_maxima,
        duracion_maxima=opciones.duracion_maxima,
        silencio_final=opciones.silencio_final,
    )
    if opciones.activacion:
        print("Cargando el detector de «Astro»...")
        cambios = {
            campo: valor
            for campo, valor in (
                ("umbral", opciones.umbral_activacion),
                ("bloques_consecutivos", opciones.bloques_activacion),
            )
            if valor is not None
        }
        detector = await asyncio.to_thread(
            DetectorActivacion,
            replace(
                configuracion_predeterminada(opciones.modelo_activacion),
                **cambios,
            ),
        )
        escucha = EscuchaContinua(
            detector,
            dispositivo=opciones.microfono,
        )

    def mostrar_activacion(activacion: Activacion) -> None:
        registrar_activacion(activacion)
        print(f"Activado ({activacion.puntuacion:.2f}). Te escucho...")

    print(f"Conectando con ASTRO en {url}...")
    token = os.getenv("ASTRO_DEVICE_TOKEN", "")
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as websocket:
        listo = json.loads(await websocket.recv())
        if listo.get("type") != "ready":
            raise RuntimeError("ASTRO no confirmó la conexión")

        print("ASTRO conectado.")
        if escucha is not None:
            print("Di «Astro» para hablar. Pulsa Ctrl+C para terminar.")
        else:
            print("Pulsa Enter para hablar o escribe 'salir' para terminar.")

        while True:
            if escucha is not None:
                print("\nDormido. Esperando «Astro»...")
                cancelar = Event()
                try:
                    resultado_escucha = await asyncio.to_thread(
                        escucha.esperar_frase,
                        RUTA_PREGUNTA,
                        configuracion_frase,
                        cancelar,
                        mostrar_activacion,
                    )
                except asyncio.CancelledError:
                    cancelar.set()
                    raise
                except ValueError as error:
                    print(f"No se pudo obtener una frase: {error}")
                    continue
                informe = resultado_escucha.informe
                microfono = escucha.nombre_dispositivo()
                desbordamientos = resultado_escucha.desbordamientos
            else:
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
            detener_audio = Event()
            terminar_escucha = Event()
            bucle = asyncio.get_running_loop()
            generado = ""
            posicion = 0

            async def confirmar(cantidad):
                await websocket.send(json.dumps({"type": "ack", "characters": cantidad}))

            async def interrumpir():
                detener_audio.set()
                await websocket.send(json.dumps({"type": "cancel"}))

            escucha = None
            if opciones.interrumpir_con_voz:
                escucha = asyncio.create_task(asyncio.to_thread(
                    escuchar_interrupcion, opciones.microfono, terminar_escucha,
                    lambda: asyncio.run_coroutine_threadsafe(interrumpir(), bucle),
                ))
            segmentador = SegmentadorTexto()
            tarea_voz = asyncio.create_task(
                reproducir_cola_streaming(
                    cola_texto,
                    voz,
                    configuracion_voz,
                    opciones.altavoz,
                    RUTA_RESPUESTA,
                    inicio_respuesta,
                    detener=detener_audio,
                    confirmar=confirmar,
                )
            )

            def mostrar_y_preparar(fragmento: str) -> None:
                nonlocal tiempo_primer_texto, tiempo_primer_fragmento
                nonlocal generado, posicion
                generado += fragmento
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
                        posicion = generado.find(parte, posicion) + len(parte)
                        cola_texto.put_nowait((texto_hablado, posicion))

            try:
                respuesta = await recibir_respuesta(
                    websocket,
                    transcripcion.texto,
                    mostrar_y_preparar,
                )
            except BaseException as error:
                detener_audio.set()
                terminar_escucha.set()
                await cola_texto.put(None)
                await tarea_voz
                if escucha:
                    await escucha
                if isinstance(error, InterruptedError):
                    print("\nRespuesta detenida. Pulsa Enter para la siguiente frase.")
                    continue
                await websocket.send(json.dumps({"type": "played", "characters": 0}))
                raise

            for parte in segmentador.finalizar():
                texto_hablado = limpiar_para_voz(parte)
                if texto_hablado:
                    await cola_texto.put((texto_hablado, len(generado)))
            await cola_texto.put(None)
            resultado_voz = await tarea_voz
            terminar_escucha.set()
            if escucha:
                await escucha
            if detener_audio.is_set():
                # done puede llegar antes de que termine el audio: consumir la confirmación de cancelación.
                while json.loads(await websocket.recv()).get("type") != "cancelled":
                    pass
                print("\nRespuesta detenida. Pulsa Enter para la siguiente frase.")
                continue
            await websocket.send(json.dumps({"type": "played", "characters": len(generado)}))
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
