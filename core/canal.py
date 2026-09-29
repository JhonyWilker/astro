"""Recepción independiente del turno: permite confirmar lectura y cancelar."""

import asyncio
import json
from time import monotonic

from fastapi import WebSocketDisconnect

from core.acceso import ROL_RESTRINGIDO
from core.turno import ControlTurno, TurnoCancelado


async def atender(
    websocket, acceso, conversaciones, serializar_uso, serializar_cambio,
    explicar_error,
):
    dispositivo = websocket.state.dispositivo
    conversacion = conversaciones.obtener(
        dispositivo.usuario,
        websocket.app.state.nucleo,
        restringida=dispositivo.rol == ROL_RESTRINGIDO,
    )
    sesion = conversacion.sesion
    await websocket.accept()
    websocket.app.state.conexiones += 1
    tarea = None
    control = None
    turno = None
    envio = asyncio.Lock()

    async def enviar(datos):
        async with envio:
            await websocket.send_json(datos)

    conversacion.conexiones[websocket] = enviar

    async def sincronizar():
        evento = {"type": "sync", "session": conversacion.identificador, "history": conversacion.historial()}
        for conexion, enviar_conexion in tuple(conversacion.conexiones.items()):
            if conexion is not websocket:
                try:
                    await enviar_conexion(evento)
                except (RuntimeError, OSError):
                    pass

    await enviar({"type": "ready", "protocol": 2, "session": conversacion.identificador, "history": conversacion.historial()})
    bucle = asyncio.get_running_loop()

    async def ejecutar(texto, edicion, indice, ctl):
        eventos = []

        def emitir(fragmento):
            ctl.comprobar()
            evento = {"type": "delta", "text": fragmento}
            if edicion:
                eventos.append(evento)
            else:
                asyncio.run_coroutine_threadsafe(enviar(evento), bucle).result(timeout=10)

        def cambio(valor):
            evento = serializar_cambio(valor)
            if edicion:
                eventos.append(evento)
            else:
                asyncio.run_coroutine_threadsafe(enviar(evento), bucle).result(timeout=10)

        def progreso(estado, herramienta=None):
            evento = {"type": "state", "state": estado}
            if herramienta is not None:
                evento["tool"] = herramienta
            if edicion:
                eventos.append(evento)
            else:
                asyncio.run_coroutine_threadsafe(
                    enviar(evento), bucle
                ).result(timeout=10)

        def expresion(direccion):
            evento = {"type": "voice_style", "direction": direccion}
            if edicion:
                eventos.append(evento)
            else:
                asyncio.run_coroutine_threadsafe(
                    enviar(evento), bucle
                ).result(timeout=10)

        try:
            if edicion:
                resultado = await asyncio.to_thread(
                    sesion.editar_turno,
                    indice,
                    texto,
                    emitir,
                    cambio,
                    ctl,
                    progreso,
                    expresion,
                )
                await enviar({"type": "rewind", "turn": indice, "text": texto})
                for evento in eventos:
                    await enviar(evento)
            else:
                resultado = await asyncio.to_thread(
                    sesion.preguntar,
                    texto,
                    emitir,
                    cambio,
                    ctl,
                    progreso,
                    expresion,
                )
            ctl.generacion_completa = True
            await enviar({
                "type": "done", "turn": indice,
                "usage": [serializar_uso(item) for item in resultado.registros],
                "provider": resultado.proveedor_final, "model": resultado.modelo_final,
                "fallback_used": bool(resultado.cambios_proveedor),
            })
        except TurnoCancelado:
            pass
        except Exception as error:
            ctl.generacion_completa = True
            await enviar({"type": "error", "message": explicar_error(error)})
        finally:
            conversacion.ultimo_uso = monotonic()
            # El bloqueo continúa hasta confirmar la reproducción/lectura.

    async def terminar(cancelar=False):
        nonlocal tarea, control
        if control is None:
            return
        if cancelar:
            await asyncio.to_thread(control.cancelar)
        if tarea:
            await asyncio.gather(tarea, return_exceptions=True)
        if cancelar and control.historial_actualizado and hasattr(sesion, "historial") and sesion.historial:
            # Solo el prefijo confirmado por el cliente pertenece al diálogo oído.
            ultimo = sesion.historial[-1]
            if ultimo["role"] == "assistant" and control.emitido.startswith(ultimo["content"]):
                ultimo["content"] = control.emitido[:control.confirmado]
        tarea = None
        control = None
        if conversacion.bloqueo.locked():
            conversacion.bloqueo.release()
        conversacion.publicado = conversacion.historial()
        await sincronizar()

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=300 if control else 86400,
                )
            except TimeoutError:
                await terminar(cancelar=True)
                await websocket.close(code=1000)
                break
            if len(raw.encode()) > 16384:
                await websocket.close(code=1009)
                break
            dispositivo_actual = acceso.identificar(dispositivo.token)
            if (
                dispositivo_actual is None
                or dispositivo_actual.usuario != dispositivo.usuario
                or dispositivo_actual.rol != dispositivo.rol
            ):
                await websocket.close(code=1008)
                break
            if not acceso.permitir((dispositivo.nombre, "frames"), 900):
                await websocket.close(code=1008)
                break
            try:
                mensaje = json.loads(raw)
            except ValueError:
                await enviar({"type": "error", "message": "JSON no válido."})
                continue
            if not isinstance(mensaje, dict):
                await enviar({"type": "error", "message": "Mensaje no válido."})
                continue
            tipo = mensaje.get("type")
            if tipo == "ack" and control:
                if not acceso.permitir((dispositivo.nombre, "ack"), 600):
                    await websocket.close(code=1008)
                    break
                control.confirmar(mensaje.get("characters"))
                continue
            if not acceso.permitir((dispositivo.nombre, "mensajes"), 30):
                await websocket.close(code=1008)
                break
            if tipo == "cancel":
                await terminar(cancelar=True)
                await enviar({"type": "cancelled", "turn": turno})
                continue
            if tipo == "played":
                if control and not control.generacion_completa:
                    await enviar({"type": "busy", "message": "El turno aún está generándose."})
                    continue
                if control:
                    control.confirmar(mensaje.get("characters"))
                await terminar()
                continue
            if tipo == "classify_direction":
                texto = mensaje.get("text")
                origen = mensaje.get("origin")
                if (
                    not isinstance(texto, str)
                    or not texto.strip()
                    or len(texto) > 4000
                    or origen not in {"activation", "followup"}
                ):
                    await enviar({
                        "type": "error",
                        "message": "Clasificación de voz no válida.",
                    })
                    continue
                if conversacion.bloqueo.locked():
                    await enviar({
                        "type": "busy",
                        "message": "Otro turno sigue activo en esta conversación.",
                    })
                    continue
                await conversacion.bloqueo.acquire()
                try:
                    resultado = await asyncio.to_thread(
                        sesion.clasificar_destinatario,
                        texto.strip(),
                        origen,
                    )
                    await enviar({
                        "type": "direction",
                        "addressed": resultado.dirigida,
                        "reason": resultado.motivo,
                        "usage": [
                            serializar_uso(item)
                            for item in resultado.registros
                        ],
                        "provider": resultado.proveedor_final,
                        "model": resultado.modelo_final,
                        "fallback_used": resultado.uso_respaldo,
                    })
                except Exception as error:
                    await enviar({
                        "type": "error",
                        "message": explicar_error(error),
                    })
                finally:
                    conversacion.ultimo_uso = monotonic()
                    conversacion.bloqueo.release()
                continue
            texto = mensaje.get("text")
            if tipo not in {"message", "edit"} or not isinstance(texto, str) or not texto.strip() or len(texto) > 4000:
                await enviar({"type": "error", "message": "Envía un texto de 1 a 4000 caracteres."})
                continue
            indice = mensaje.get("turn")
            if tipo == "edit" and (type(indice) is not int or indice < 0):
                await enviar({"type": "error", "message": "Turno no válido."})
                continue
            if conversacion.bloqueo.locked():
                await enviar({"type": "busy", "message": "Otro turno sigue activo en esta conversación."})
                continue
            await conversacion.bloqueo.acquire()
            turno = indice if tipo == "edit" else sesion.cantidad_turnos
            control = ControlTurno()
            tarea = asyncio.create_task(ejecutar(texto.strip(), tipo == "edit", turno, control))
    except WebSocketDisconnect:
        pass
    finally:
        conversacion.conexiones.pop(websocket, None)
        await terminar(cancelar=True)
        conversacion.ultimo_uso = monotonic()
        websocket.app.state.conexiones -= 1
