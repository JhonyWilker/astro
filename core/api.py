import asyncio
from contextlib import asynccontextmanager
from json import JSONDecodeError
from pathlib import Path
from time import monotonic
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.chat import explicar_error
from core.errores import ErrorRespuestaASTRO
from core.notificaciones import ErrorNotificaciones, ServicioNotificaciones
from core.sesion import NucleoASTRO, crear_nucleo
from core.uso import RegistroUso

RUTA_WEB = Path(__file__).resolve().parents[1] / "clients" / "web"
RUTA_INDEX = RUTA_WEB / "index.html"
RUTA_MANIFIESTO = RUTA_WEB / "manifest.webmanifest"
RUTA_SERVICE_WORKER = RUTA_WEB / "service-worker.js"


class ClavesPush(BaseModel):
    p256dh: str = Field(min_length=16, max_length=512)
    auth: str = Field(min_length=8, max_length=256)


class SuscripcionPushEntrada(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    endpoint: str = Field(max_length=2048)
    expiration_time: int | None = Field(
        default=None,
        alias="expirationTime",
    )
    keys: ClavesPush

    @field_validator("endpoint")
    @classmethod
    def endpoint_https(cls, valor: str) -> str:
        if not valor.startswith("https://"):
            raise ValueError("El endpoint debe usar HTTPS")
        return valor


class EndpointPush(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)


def serializar_uso(registro: RegistroUso) -> dict[str, int | float]:
    return {
        "tokens": registro.tokens_totales,
        "segundos": registro.duracion_segundos,
        "coste_estimado_usd": registro.coste_estimado_usd,
    }


def crear_app(
    nucleo: NucleoASTRO | None = None,
    notificaciones: ServicioNotificaciones | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(aplicacion: FastAPI) -> AsyncIterator[None]:
        if aplicacion.state.nucleo is None:
            aplicacion.state.nucleo = crear_nucleo()
        if aplicacion.state.notificaciones is None:
            aplicacion.state.notificaciones = (
                ServicioNotificaciones.desde_entorno()
            )
        yield

    aplicacion = FastAPI(
        title="ASTRO Core",
        version="0.1",
        lifespan=lifespan,
    )
    aplicacion.state.nucleo = nucleo
    aplicacion.state.notificaciones = notificaciones
    aplicacion.state.inicio = monotonic()
    aplicacion.state.conexiones = 0

    @aplicacion.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "astro-core"}

    @aplicacion.get("/status")
    async def status() -> dict:
        servicio = aplicacion.state.notificaciones
        try:
            suscripciones = servicio.contar()
        except ErrorNotificaciones:
            suscripciones = 0
        configuracion = getattr(
            aplicacion.state.nucleo,
            "configuracion",
            None,
        )
        return {
            "status": "ok",
            "version": aplicacion.version,
            "model": getattr(configuracion, "modelo", "desconocido"),
            "uptime_seconds": int(monotonic() - aplicacion.state.inicio),
            "websocket_connections": aplicacion.state.conexiones,
            "push": {
                "configured": servicio.configurado,
                "subscriptions": suscripciones,
            },
        }

    @aplicacion.get("/push/public-key")
    async def push_public_key() -> dict[str, str]:
        servicio = aplicacion.state.notificaciones
        if not servicio.configurado:
            raise HTTPException(
                status_code=503,
                detail="Las notificaciones no están configuradas",
            )
        return {"public_key": servicio.clave_publica}

    @aplicacion.post("/push/subscribe")
    async def push_subscribe(
        entrada: SuscripcionPushEntrada,
    ) -> dict[str, int | bool]:
        servicio = aplicacion.state.notificaciones
        if not servicio.configurado:
            raise HTTPException(
                status_code=503,
                detail="Las notificaciones no están configuradas",
            )
        try:
            cantidad = servicio.guardar(
                entrada.model_dump(by_alias=True)
            )
        except (ErrorNotificaciones, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"subscribed": True, "subscriptions": cantidad}

    @aplicacion.post("/push/unsubscribe")
    async def push_unsubscribe(
        entrada: EndpointPush,
    ) -> dict[str, int | bool]:
        servicio = aplicacion.state.notificaciones
        try:
            cantidad = servicio.eliminar(entrada.endpoint)
        except ErrorNotificaciones as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return {"subscribed": False, "subscriptions": cantidad}

    @aplicacion.post("/push/test")
    async def push_test() -> dict[str, int]:
        servicio = aplicacion.state.notificaciones
        try:
            enviados, fallos = await asyncio.to_thread(
                servicio.enviar_prueba
            )
        except ErrorNotificaciones as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {"sent": enviados, "failed": fallos}

    @aplicacion.get("/", response_class=HTMLResponse)
    async def web() -> HTMLResponse:
        return HTMLResponse(RUTA_INDEX.read_text(encoding="utf-8"))

    @aplicacion.get(
        "/manifest.webmanifest",
        response_class=FileResponse,
        include_in_schema=False,
    )
    async def manifiesto() -> FileResponse:
        return FileResponse(
            RUTA_MANIFIESTO,
            media_type="application/manifest+json",
        )

    @aplicacion.get(
        "/service-worker.js",
        response_class=FileResponse,
        include_in_schema=False,
    )
    async def service_worker() -> FileResponse:
        return FileResponse(
            RUTA_SERVICE_WORKER,
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @aplicacion.websocket("/ws")
    async def websocket_chat(websocket: WebSocket) -> None:
        await websocket.accept()
        websocket.app.state.conexiones += 1
        sesion = websocket.app.state.nucleo.nueva_sesion()
        await websocket.send_json({"type": "ready"})
        bucle = asyncio.get_running_loop()

        try:
            while True:
                try:
                    mensaje = await websocket.receive_json()
                except JSONDecodeError:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "El mensaje debe ser JSON válido.",
                        }
                    )
                    continue

                if (
                    not isinstance(mensaje, dict)
                    or mensaje.get("type") != "message"
                    or not isinstance(mensaje.get("text"), str)
                    or not mensaje["text"].strip()
                ):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Envía un mensaje de texto no vacío.",
                        }
                    )
                    continue

                def emitir_texto(fragmento: str) -> None:
                    futuro = asyncio.run_coroutine_threadsafe(
                        websocket.send_json(
                            {"type": "delta", "text": fragmento}
                        ),
                        bucle,
                    )
                    futuro.result()

                try:
                    resultado = await asyncio.to_thread(
                        sesion.preguntar,
                        mensaje["text"],
                        emitir_texto,
                    )
                except (APIError, ErrorRespuestaASTRO) as error:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": explicar_error(error),
                        }
                    )
                    continue

                await websocket.send_json(
                    {
                        "type": "done",
                        "usage": [
                            serializar_uso(registro)
                            for registro in resultado.registros
                        ],
                    }
                )
        except WebSocketDisconnect:
            pass
        finally:
            websocket.app.state.conexiones = max(
                0,
                websocket.app.state.conexiones - 1,
            )

    aplicacion.mount(
        "/static",
        StaticFiles(directory=RUTA_WEB),
        name="static",
    )

    return aplicacion


app = crear_app()
