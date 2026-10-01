import asyncio
import json
import os
import re
from argparse import ArgumentParser
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from threading import Event
from typing import Any, Callable

import websockets
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed

from core.chat import cargar_personalidad
from core.expresion import INSTRUCCIONES_VOZ, ParserExpresionVoz
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
from voice.eco import CanceladorEco
from voice.hablar import (
    cargar_voz,
    crear_configuracion,
)
from voice.streaming import SegmentadorTexto, reproducir_cola_streaming
from voice.proveedor_voz import crear_sintetizador_voz
from voice.interrupcion import (
    ControlInterrupcion,
    DetectorInterrupcionEco,
    es_orden_silencio,
    transcripcion_interrupcion_fiable,
)
from voice.realtime_prueba import ErrorRealtimePrueba, SesionRealtimePrueba
from voice.seguimiento import VentanaSeguimiento
from voice.puente import PuenteLocal
from voice.destinatario import (
    clasificar_destinatario_local,
    registrar_falso_positivo,
)
from voice.detectar_voz import (
    ConfiguracionDeteccion,
    grabar_hasta_silencio,
)
from voice.transcribir import (
    MODELO_PREDETERMINADO,
    cargar_modelo_preferido,
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
    decision_local = clasificar_destinatario_local(texto)
    if decision_local is not None:
        dirigida, motivo = decision_local
        return DireccionRemota(
            dirigida=dirigida,
            motivo=motivo,
            peticiones=0,
            tokens=0,
            coste_usd=0.0,
        )
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
    cambiar_expresion: Callable[[str], None] | None = None,
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
        elif tipo == "voice_style":
            direccion = evento.get("direction")
            if not isinstance(direccion, str) or not direccion.strip():
                raise RuntimeError("ASTRO envió una expresión de voz no válida")
            if cambiar_expresion is not None:
                cambiar_expresion(direccion.strip())
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


async def responder_realtime_hablado(
    sesion: SesionRealtimePrueba,
    ruta_audio: Path,
    sintetizador: Any,
    voz: Any,
    configuracion_voz: Any,
    altavoz: int | None,
    microfono: int | None,
    detector_eco: Any | None,
    indicador: IndicadorEstados,
    inicio: float,
    silencio_final: float,
) -> tuple[bool, bool, bool]:
    """Prueba Realtime; devuelve False si debe usarse la ruta clásica."""
    cola_texto: asyncio.Queue[Any] = asyncio.Queue()
    control = ControlInterrupcion()
    bucle = asyncio.get_running_loop()
    generado = ""
    posicion = 0
    expresion_actual: str | None = None
    primer_texto: float | None = None
    primer_fragmento: float | None = None
    segmentador = SegmentadorTexto()

    async def confirmar(_cantidad: int) -> None:
        return

    def avisar_interrupcion() -> None:
        asyncio.run_coroutine_threadsafe(sesion.cancelar(), bucle)

    tarea_voz = asyncio.create_task(reproducir_cola_streaming(
        cola_texto,
        voz,
        configuracion_voz,
        altavoz,
        RUTA_RESPUESTA,
        inicio,
        sintetizador=sintetizador,
        detener=control,
        confirmar=confirmar,
        al_empezar=lambda: indicador.cambiar(
            EstadoVoz.HABLANDO,
            sonido=False,
        ),
        microfono=microfono,
        detector_eco=detector_eco,
        al_detectar=avisar_interrupcion,
        turno_continuo=True,
    ))

    def mostrar_y_preparar(fragmento: str) -> None:
        nonlocal generado, posicion, primer_texto, primer_fragmento
        generado += fragmento
        ahora = perf_counter()
        if primer_texto is None:
            primer_texto = ahora - inicio
        print(fragmento, end="", flush=True)
        partes = segmentador.agregar(fragmento)
        if partes and primer_fragmento is None:
            primer_fragmento = ahora - inicio
        for parte in partes:
            texto_hablado = limpiar_para_voz(parte)
            if texto_hablado:
                posicion = generado.find(parte, posicion) + len(parte)
                cola_texto.put_nowait(
                    (texto_hablado, posicion, expresion_actual)
                )

    def cambiar_expresion(direccion: str) -> None:
        nonlocal expresion_actual
        expresion_actual = direccion

    parser = ParserExpresionVoz(mostrar_y_preparar, cambiar_expresion)
    respuesta_realtime = None
    try:
        respuesta_realtime = await sesion.responder(ruta_audio, parser.agregar)
        parser.finalizar()
    except ErrorRealtimePrueba as error:
        parser.finalizar()
        if not generado:
            control.evento.set()
            await cola_texto.put(None)
            await tarea_voz
            print(f"Realtime no disponible ({error}); vuelvo a la ruta local.")
            return False, False, False
        print(f"\nRealtime se interrumpió después de comenzar: {error}")

    if (
        respuesta_realtime is not None
        and respuesta_realtime.ordenar_silencio
    ):
        control.evento.set()
        await cola_texto.put(None)
        await tarea_voz
        print("Orden de silencio reconocida por Realtime.")
        return True, False, True

    for parte in segmentador.finalizar():
        if primer_fragmento is None:
            primer_fragmento = perf_counter() - inicio
        texto_hablado = limpiar_para_voz(parte)
        if texto_hablado:
            await cola_texto.put(
                (texto_hablado, len(generado), expresion_actual)
            )
    await cola_texto.put(None)
    resultado_voz = await tarea_voz

    if control.is_set():
        latencia = control.latencia_segundos
        detalle = f" en {latencia * 1000:.0f} ms" if latencia is not None else ""
        print(f"\nRespuesta Realtime detenida{detalle}.")
        return True, True, False
    if primer_texto is None or primer_fragmento is None:
        raise RuntimeError("Realtime no produjo una respuesta medible")
    print()
    print(
        "Latencia Realtime: "
        f"primer texto {primer_texto:.2f} s · "
        f"primer fragmento {primer_fragmento:.2f} s · "
        f"primera voz {resultado_voz.latencia_primera_voz:.2f} s"
    )
    print(
        "Primera voz real estimada desde que terminaste: "
        f"{resultado_voz.latencia_primera_voz + silencio_final:.2f} s"
    )
    return True, False, False


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
        default=0.5,
    )
    argumentos.add_argument("--microfono", type=int)
    argumentos.add_argument(
        "--activacion",
        action="store_true",
        help="Esperar la palabra de activación en vez de pulsar Enter.",
    )
    argumentos.add_argument(
        "--realtime-prueba",
        action="store_true",
        help="Probar conversación rápida con OpenAI Realtime y ElevenLabs.",
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
    argumentos.add_argument(
        "--puente",
        action="store_true",
        help="Publicar el estado de la voz por un WebSocket local (127.0.0.1).",
    )
    interrupcion = argumentos.add_mutually_exclusive_group()
    interrupcion.add_argument(
        "--interrumpir-con-voz",
        dest="interrumpir_con_voz",
        action="store_true",
        help="Escuchar mientras responde y retirar su propia voz con AEC3.",
    )
    interrupcion.add_argument(
        "--sin-interrumpir-con-voz",
        dest="interrumpir_con_voz",
        action="store_false",
        help="Desactivar expresamente la interrupción por voz.",
    )
    argumentos.set_defaults(interrumpir_con_voz=True)
    argumentos.add_argument(
        "--retardo-eco",
        type=int,
        default=0,
        help="Retardo altavoz-micrófono para WebRTC AEC3 (0-500 ms).",
    )
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

    print(f"Cargando Whisper {opciones.modelo}...")
    modelo, dispositivo_stt = await asyncio.to_thread(
        cargar_modelo_preferido,
        opciones.modelo,
    )
    print(f"Whisper activo en {dispositivo_stt.upper()}.")
    print("Cargando la voz local de respaldo de ASTRO...")
    voz = await asyncio.to_thread(cargar_voz)
    configuracion_voz = crear_configuracion(opciones.hablante)
    sintetizador_voz = crear_sintetizador_voz(voz, configuracion_voz)
    if sintetizador_voz.principal_disponible:
        print(
            "Voz principal: ASTRO expresivo en ElevenLabs "
            f"{sintetizador_voz.configuracion.modelo}; respaldo: Piper."
        )
    else:
        print("Voz principal no disponible; se usará Piper como respaldo.")
    indicador = IndicadorEstados(
        dispositivo=opciones.altavoz,
        sonidos=not opciones.sin_sonidos_estado,
    )
    cancelador_eco = (
        CanceladorEco(opciones.retardo_eco)
        if opciones.interrumpir_con_voz
        else None
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
            indicador.cambiar(EstadoVoz.EJECUTANDO, detalle, sonido=False)
        elif estado == "thinking":
            indicador.cambiar(EstadoVoz.PENSANDO, sonido=False)

    print(f"Conectando con ASTRO en {url}...")
    token = os.getenv("ASTRO_DEVICE_TOKEN", "")
    puente = None
    if opciones.puente:
        puente = PuenteLocal()
        if puente.iniciar():
            indicador.al_cambiar = puente.publicar_estado
            print(f"Puente local activo en 127.0.0.1:{puente.puerto}.")
        else:
            print("No se pudo iniciar el puente local; la voz continúa sin él.")
            puente = None
    async with AsyncExitStack() as recursos:
        if puente is not None:
            recursos.callback(puente.detener)
        websocket = await recursos.enter_async_context(websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {token}"},
        ))
        listo = json.loads(await websocket.recv())
        if listo.get("type") != "ready":
            raise RuntimeError("ASTRO no confirmó la conexión")

        print("ASTRO conectado.")
        sesion_realtime = None
        if opciones.realtime_prueba:
            instrucciones_realtime = (
                cargar_personalidad()
                + "\n\n"
                + INSTRUCCIONES_VOZ
                + "\n\nEsta ruta es una prueba conversacional. No uses "
                "herramientas, no ejecutes acciones y responde de forma breve."
            )
            try:
                sesion_realtime = await recursos.enter_async_context(
                    SesionRealtimePrueba(instrucciones_realtime)
                )
                print("Modo de prueba: OpenAI Realtime + ElevenLabs.")
            except ErrorRealtimePrueba as error:
                print(f"Realtime no pudo iniciarse ({error}); usaré la ruta local.")
        if escucha_activacion is not None:
            print("Di «Astro» para hablar. Pulsa Ctrl+C para terminar.")
        else:
            print("Pulsa Enter para hablar o escribe 'salir' para terminar.")

        indicador.cambiar(EstadoVoz.DORMIDO)
        audio_interrupcion_pendiente: bytes | None = None
        while True:
            es_seguimiento = (
                escucha_activacion is not None
                and ventana_seguimiento.activa
            )
            if es_seguimiento:
                cancelar = Event()
                audio_inicial = audio_interrupcion_pendiente or b""
                venia_de_interrupcion = bool(audio_inicial)
                audio_interrupcion_pendiente = None
                try:
                    resultado_frase = await asyncio.to_thread(
                        escucha_activacion.esperar_seguimiento,
                        RUTA_PREGUNTA,
                        configuracion_seguimiento,
                        cancelar,
                        audio_inicial=audio_inicial,
                        voz_inicial_confirmada=venia_de_interrupcion,
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
                venia_de_interrupcion = False
            else:
                venia_de_interrupcion = False
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
            transcripcion_interrupcion = None
            if venia_de_interrupcion:
                try:
                    transcripcion_interrupcion = await asyncio.to_thread(
                        transcribir_audio,
                        RUTA_PREGUNTA,
                        modelo,
                    )
                except ValueError:
                    transcripcion_interrupcion = None
                if (
                    transcripcion_interrupcion is None
                    or not transcripcion_interrupcion_fiable(
                        transcripcion_interrupcion
                    )
                ):
                    print(
                        "Interrupción sin una frase fiable; "
                        "ASTRO vuelve a dormir."
                    )
                    ventana_seguimiento.cerrar()
                    indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
                print(
                    "Interrupción entendida: "
                    f"{transcripcion_interrupcion.texto}"
                )
                if (
                    es_orden_silencio(transcripcion_interrupcion.texto)
                ):
                    print(
                        "Orden de silencio reconocida; "
                        "ASTRO vuelve a dormir."
                    )
                    ventana_seguimiento.cerrar()
                    indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
            inicio_respuesta = perf_counter()
            if sesion_realtime is not None:
                indicador.cambiar(
                    EstadoVoz.PENSANDO,
                    "Realtime",
                    sonido=False,
                )
                print("Jhony: [audio enviado a Realtime]")
                print("ASTRO: ", end="", flush=True)
                detector_realtime = (
                    DetectorInterrupcionEco(cancelador_eco)
                    if opciones.interrumpir_con_voz
                    else None
                )
                atendido, interrumpido, ordenar_silencio = (
                    await responder_realtime_hablado(
                    sesion_realtime,
                    RUTA_PREGUNTA,
                    sintetizador_voz,
                    voz,
                    configuracion_voz,
                    opciones.altavoz,
                    opciones.microfono,
                    detector_realtime,
                    indicador,
                    inicio_respuesta,
                    opciones.silencio_final,
                    )
                )
                if atendido:
                    if es_seguimiento:
                        ventana_seguimiento.consumir()
                    if ordenar_silencio:
                        ventana_seguimiento.cerrar()
                        indicador.cambiar(EstadoVoz.DORMIDO)
                    elif interrumpido:
                        audio_interrupcion_pendiente = (
                            detector_realtime.extraer_audio_interrupcion()
                            if detector_realtime is not None
                            else b""
                        )
                        if audio_interrupcion_pendiente:
                            if not ventana_seguimiento.activa:
                                ventana_seguimiento.abrir()
                            indicador.cambiar(
                                EstadoVoz.ESCUCHANDO,
                                "Te escucho",
                                sonido=False,
                            )
                        else:
                            ventana_seguimiento.cerrar()
                            indicador.cambiar(EstadoVoz.DORMIDO)
                    elif escucha_activacion is not None and ventana_seguimiento.activa:
                        indicador.cambiar(
                            EstadoVoz.ESCUCHANDO,
                            "Puedes continuar · quedan "
                            f"{ventana_seguimiento.restantes}",
                        )
                    else:
                        indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
            indicador.cambiar(
                EstadoVoz.PENSANDO,
                "Transcribiendo",
                sonido=False,
            )
            try:
                transcripcion = (
                    transcripcion_interrupcion
                    if transcripcion_interrupcion is not None
                    else await asyncio.to_thread(
                        transcribir_audio,
                        RUTA_PREGUNTA,
                        modelo,
                    )
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
                    sonido=False,
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
            if puente is not None:
                puente.publicar("transcript", text=transcripcion.texto)
            print("ASTRO: ", end="", flush=True)

            cola_texto: asyncio.Queue[str | None] = asyncio.Queue()
            control_interrupcion = ControlInterrupcion()
            detener_audio = control_interrupcion
            detector_eco = (
                DetectorInterrupcionEco(cancelador_eco)
                if opciones.interrumpir_con_voz
                else None
            )
            bucle = asyncio.get_running_loop()
            generado = ""
            posicion = 0
            expresion_actual: str | None = None

            async def confirmar(cantidad):
                await websocket.send(json.dumps({"type": "ack", "characters": cantidad}))

            async def interrumpir():
                await websocket.send(json.dumps({"type": "cancel"}))

            def avisar_interrupcion() -> None:
                asyncio.run_coroutine_threadsafe(interrumpir(), bucle)

            segmentador = SegmentadorTexto()
            tarea_voz = asyncio.create_task(
                reproducir_cola_streaming(
                    cola_texto,
                    voz,
                    configuracion_voz,
                    opciones.altavoz,
                    RUTA_RESPUESTA,
                    inicio_respuesta,
                    sintetizador=sintetizador_voz,
                    detener=detener_audio,
                    confirmar=confirmar,
                    al_empezar=lambda: indicador.cambiar(
                        EstadoVoz.HABLANDO,
                        sonido=False,
                    ),
                    microfono=opciones.microfono,
                    detector_eco=detector_eco,
                    al_detectar=avisar_interrupcion,
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
                        cola_texto.put_nowait(
                            (texto_hablado, posicion, expresion_actual)
                        )

            def cambiar_expresion(direccion: str) -> None:
                nonlocal expresion_actual
                expresion_actual = direccion

            try:
                respuesta = await recibir_respuesta(
                    websocket,
                    transcripcion.texto,
                    mostrar_y_preparar,
                    mostrar_estado_remoto,
                    cambiar_expresion,
                )
            except BaseException as error:
                control_interrupcion.evento.set()
                await cola_texto.put(None)
                resultado_voz = await tarea_voz
                if isinstance(error, InterruptedError):
                    audio_interrupcion_pendiente = (
                        detector_eco.extraer_audio_interrupcion()
                        if detector_eco is not None
                        else b""
                    )
                    latencia = control_interrupcion.latencia_segundos
                    detalle = (
                        f" en {latencia * 1000:.0f} ms"
                        if latencia is not None
                        else ""
                    )
                    print(f"\nRespuesta detenida{detalle}.")
                    if audio_interrupcion_pendiente:
                        if not ventana_seguimiento.activa:
                            ventana_seguimiento.abrir()
                        indicador.cambiar(
                            EstadoVoz.ESCUCHANDO,
                            "Te escucho",
                            sonido=False,
                        )
                    else:
                        ventana_seguimiento.cerrar()
                        indicador.cambiar(EstadoVoz.DORMIDO)
                    continue
                await websocket.send(json.dumps({"type": "played", "characters": 0}))
                raise

            for parte in segmentador.finalizar():
                if tiempo_primer_fragmento is None:
                    tiempo_primer_fragmento = perf_counter() - inicio_respuesta
                texto_hablado = limpiar_para_voz(parte)
                if texto_hablado:
                    await cola_texto.put(
                        (texto_hablado, len(generado), expresion_actual)
                    )
            await cola_texto.put(None)
            resultado_voz = await tarea_voz
            if detener_audio.is_set():
                # done puede llegar antes de que termine el audio: consumir la confirmación de cancelación.
                while json.loads(await websocket.recv()).get("type") != "cancelled":
                    pass
                audio_interrupcion_pendiente = (
                    detector_eco.extraer_audio_interrupcion()
                    if detector_eco is not None
                    else b""
                )
                latencia = control_interrupcion.latencia_segundos
                detalle = (
                    f" en {latencia * 1000:.0f} ms"
                    if latencia is not None
                    else ""
                )
                print(f"\nRespuesta detenida{detalle}.")
                if audio_interrupcion_pendiente:
                    if not ventana_seguimiento.activa:
                        ventana_seguimiento.abrir()
                    indicador.cambiar(
                        EstadoVoz.ESCUCHANDO,
                        "Te escucho",
                        sonido=False,
                    )
                else:
                    ventana_seguimiento.cerrar()
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
            print(
                "Primera voz real estimada desde que terminaste: "
                f"{resultado_voz.latencia_primera_voz + opciones.silencio_final:.2f} s "
                f"(incluye {opciones.silencio_final:.2f} s para confirmar el final)"
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
