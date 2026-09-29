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
from voice.escucha import (
    ConfiguracionFrase,
    EscuchaContinua,
    validar_configuracion as validar_configuracion_frase,
)
from voice.estados import EstadoVoz, IndicadorEstados
from voice.hablar import (
    cargar_voz,
    crear_configuracion,
)
from voice.streaming import SegmentadorTexto, reproducir_cola_streaming
from voice.interrupcion import escuchar_interrupcion
from voice.seguimiento import VentanaSeguimiento
from voice.destinatario import registrar_falso_positivo
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


@dataclass(frozen=True)
class DireccionRemota:
    dirigida: bool
    motivo: str
    peticiones: int
    tokens: int
    coste_usd: float


def confirmar_activacion() -> DireccionRemota:
    """La palabra de activación ya confirmó a quién iba la frase."""
    return DireccionRemota(
        dirigida=True,
        motivo="direct_mention",
        peticiones=0,
        tokens=0,
        coste_usd=0.0,
    )


async def comprobar_destinatario(
    websocket: Any,
    texto: str,
    origen: str,
) -> DireccionRemota:
    await websocket.send(json.dumps({
        "type": "classify_direction",
        "text": texto,
        "origin": origen,
    }, ensure_ascii=False))
    evento = json.loads(await websocket.recv())
    tipo = evento.get("type")
    if tipo == "error":
        raise RuntimeError(
            str(evento.get("message", "No se pudo comprobar el destinatario"))
        )
    if tipo == "busy":
        raise RuntimeError("Hay otro turno activo en esta conversación")
    if tipo != "direction":
        raise RuntimeError("ASTRO no confirmó el destinatario de la frase")
    uso = evento.get("usage", [])
    return DireccionRemota(
        dirigida=evento.get("addressed") is True,
        motivo=str(evento.get("reason", "uncertain")),
        peticiones=len(uso),
        tokens=sum(int(item["tokens"]) for item in uso),
        coste_usd=sum(float(item["coste_estimado_usd"]) for item in uso),
    )


def limpiar_para_voz(texto: str) -> str:
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    texto = re.sub(r"[`*_#]", "", texto)
    return " ".join(texto.split())


async def recibir_respuesta(
    websocket: Any,
    texto: str,
    mostrar_fragmento: Callable[[str], None] | None = None,
    cambiar_estado: Callable[[str, str | None], None] | None = None,
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
        elif tipo == "state":
            estado = str(evento.get("state", ""))
            if estado not in {"thinking", "executing"}:
                raise RuntimeError(
                    f"ASTRO envió un estado desconocido: {estado or 'vacío'}"
                )
            if cambiar_estado is not None:
                herramienta = evento.get("tool")
                cambiar_estado(
                    estado,
                    str(herramienta) if herramienta is not None else None,
                )
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
    argumentos.add_argument(
        "--turnos-seguimiento",
        type=int,
        default=5,
        help="Intervenciones adicionales sin repetir «Astro» (1-10).",
    )
    argumentos.add_argument(
        "--espera-seguimiento",
        type=float,
        default=8.0,
        help="Segundos para comenzar cada seguimiento (0,1-60).",
    )
    argumentos.add_argument("--altavoz", type=int)
    argumentos.add_argument(
        "--sin-sonidos-estado",
        action="store_true",
        help="Mostrar los estados sin reproducir sus señales sonoras.",
    )
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
    indicador = IndicadorEstados(
        dispositivo=opciones.altavoz,
        sonidos=not opciones.sin_sonidos_estado,
    )

    escucha_activacion = None
    configuracion_frase = ConfiguracionFrase(
        espera_maxima=opciones.espera_maxima,
        duracion_maxima=opciones.duracion_maxima,
        silencio_final=opciones.silencio_final,
    )
    configuracion_seguimiento = ConfiguracionFrase(
        espera_maxima=opciones.espera_seguimiento,
        duracion_maxima=opciones.duracion_maxima,
        silencio_final=opciones.silencio_final,
    )
    validar_configuracion_frase(configuracion_seguimiento)
    ventana_seguimiento = VentanaSeguimiento(
        limite=opciones.turnos_seguimiento
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
        escucha_activacion = EscuchaContinua(
            detector,
            dispositivo=opciones.microfono,
        )

    def mostrar_activacion(activacion: Activacion) -> None:
        registrar_activacion(activacion)
        indicador.cambiar(
            EstadoVoz.ESCUCHANDO,
            f"Habla ahora · activación {activacion.puntuacion:.2f}",
        )

    def mostrar_estado_remoto(
        estado: str,
        herramienta: str | None,
    ) -> None:
        if estado == "executing":
            detalle = (herramienta or "herramienta").replace("_", " ")
            indicador.cambiar(EstadoVoz.EJECUTANDO, detalle)
        elif estado == "thinking":
            indicador.cambiar(EstadoVoz.PENSANDO)

    print(f"Conectando con ASTRO en {url}...")
    token = os.getenv("ASTRO_DEVICE_TOKEN", "")
    async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as websocket:
        listo = json.loads(await websocket.recv())
        if listo.get("type") != "ready":
            raise RuntimeError("ASTRO no confirmó la conexión")

        print("ASTRO conectado.")
        if escucha_activacion is not None:
            print("Di «Astro» para hablar. Pulsa Ctrl+C para terminar.")
        else:
            print("Pulsa Enter para hablar o escribe 'salir' para terminar.")

        indicador.cambiar(EstadoVoz.DORMIDO)
        while True:
            es_seguimiento = (
                escucha_activacion is not None
                and ventana_seguimiento.activa
            )
            if es_seguimiento:
                cancelar = Event()
                try:
                    resultado_frase = await asyncio.to_thread(
                        escucha_activacion.esperar_seguimiento,
                        RUTA_PREGUNTA,
                        configuracion_seguimiento,
                        cancelar,
                    )
                except asyncio.CancelledError:
                    cancelar.set()
                    raise
                except ValueError:
                    ventana_seguimiento.cerrar()
                    print("Ventana de seguimiento cerrada por inactividad.")
                    indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
                informe = resultado_frase.informe
                microfono = escucha_activacion.nombre_dispositivo()
                desbordamientos = resultado_frase.desbordamientos
            elif escucha_activacion is not None:
                cancelar = Event()
                try:
                    resultado_escucha = await asyncio.to_thread(
                        escucha_activacion.esperar_frase,
                        RUTA_PREGUNTA,
                        configuracion_frase,
                        cancelar,
                        mostrar_activacion,
                    )
                except asyncio.CancelledError:
                    cancelar.set()
                    raise
                except ValueError as error:
                    ventana_seguimiento.cerrar()
                    print(f"No se pudo obtener una frase: {error}")
                    indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
                ventana_seguimiento.abrir()
                informe = resultado_escucha.informe
                microfono = escucha_activacion.nombre_dispositivo()
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

                indicador.cambiar(EstadoVoz.ESCUCHANDO)
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
                    indicador.cambiar(EstadoVoz.DORMIDO)
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
            indicador.cambiar(EstadoVoz.PENSANDO, "Transcribiendo")
            try:
                transcripcion = await asyncio.to_thread(
                    transcribir_audio,
                    RUTA_PREGUNTA,
                    modelo,
                )
            except ValueError as error:
                print(f"No se pudo transcribir la frase: {error}")
                if es_seguimiento:
                    indicador.cambiar(
                        EstadoVoz.ESCUCHANDO,
                        "No te entendí · inténtalo otra vez · quedan "
                        f"{ventana_seguimiento.restantes}",
                    )
                else:
                    ventana_seguimiento.cerrar()
                    indicador.cambiar(EstadoVoz.DORMIDO)
                continue
            tiempo_transcripcion = perf_counter() - inicio_respuesta
            origen = "followup" if es_seguimiento else "activation"
            if es_seguimiento:
                indicador.cambiar(
                    EstadoVoz.PENSANDO,
                    "Comprobando destinatario",
                )
                try:
                    direccion = await comprobar_destinatario(
                        websocket,
                        transcripcion.texto,
                        origen,
                    )
                except RuntimeError as error:
                    ventana_seguimiento.cerrar()
                    print(f"No pude comprobar si me hablabas: {error}")
                    indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
            else:
                # El detector ya oyó «Astro»; la grabación empieza después.
                direccion = confirmar_activacion()
            if not direccion.dirigida:
                registrar_falso_positivo(
                    origen,
                    direccion.motivo,
                    len(transcripcion.texto),
                )
                ventana_seguimiento.cerrar()
                print(
                    "Frase ajena descartada "
                    f"({direccion.motivo}); ASTRO vuelve a dormir."
                )
                print(
                    f"[{direccion.peticiones} petición/es de clasificación | "
                    f"{direccion.tokens} tokens | "
                    f"{direccion.coste_usd:.6f} USD estimados]"
                )
                indicador.cambiar(EstadoVoz.DORMIDO)
                continue
            if es_seguimiento:
                ventana_seguimiento.consumir()
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

            tarea_interrupcion = None
            if opciones.interrumpir_con_voz:
                tarea_interrupcion = asyncio.create_task(asyncio.to_thread(
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
                    al_empezar=lambda: indicador.cambiar(
                        EstadoVoz.HABLANDO
                    ),
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
                    mostrar_estado_remoto,
                )
            except BaseException as error:
                detener_audio.set()
                terminar_escucha.set()
                await cola_texto.put(None)
                await tarea_voz
                if tarea_interrupcion:
                    await tarea_interrupcion
                if isinstance(error, InterruptedError):
                    ventana_seguimiento.cerrar()
                    print("\nRespuesta detenida. Pulsa Enter para la siguiente frase.")
                    indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
                await websocket.send(json.dumps({"type": "played", "characters": 0}))
                raise

            for parte in segmentador.finalizar():
                if tiempo_primer_fragmento is None:
                    tiempo_primer_fragmento = perf_counter() - inicio_respuesta
                texto_hablado = limpiar_para_voz(parte)
                if texto_hablado:
                    await cola_texto.put((texto_hablado, len(generado)))
            await cola_texto.put(None)
            resultado_voz = await tarea_voz
            terminar_escucha.set()
            if tarea_interrupcion:
                await tarea_interrupcion
            if detener_audio.is_set():
                # done puede llegar antes de que termine el audio: consumir la confirmación de cancelación.
                while json.loads(await websocket.recv()).get("type") != "cancelled":
                    pass
                ventana_seguimiento.cerrar()
                print("\nRespuesta detenida. Pulsa Enter para la siguiente frase.")
                indicador.cambiar(EstadoVoz.DORMIDO)
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
                f"[{respuesta.peticiones + direccion.peticiones} petición/es | "
                f"{respuesta.tokens + direccion.tokens} tokens | "
                f"{respuesta.coste_usd + direccion.coste_usd:.6f} USD estimados]"
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
            if escucha_activacion is not None and ventana_seguimiento.activa:
                indicador.cambiar(
                    EstadoVoz.ESCUCHANDO,
                    "Puedes continuar · quedan "
                    f"{ventana_seguimiento.restantes}",
                )
            else:
                indicador.cambiar(EstadoVoz.DORMIDO)


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
