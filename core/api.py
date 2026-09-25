import asyncio
from contextlib import asynccontextmanager
from json import JSONDecodeError
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError

from core.chat import explicar_error
from core.errores import ErrorRespuestaASTRO
from core.sesion import NucleoASTRO, crear_nucleo
from core.uso import RegistroUso

RUTA_WEB = Path(__file__).resolve().parents[1] / "clients" / "web"
RUTA_INDEX = RUTA_WEB / "index.html"
RUTA_MANIFIESTO = RUTA_WEB / "manifest.webmanifest"
RUTA_SERVICE_WORKER = RUTA_WEB / "service-worker.js"


def serializar_uso(registro: RegistroUso) -> dict[str, int | float]:
    return {
        "tokens": registro.tokens_totales,
        "segundos": registro.duracion_segundos,
        "coste_estimado_usd": registro.coste_estimado_usd,
    }


def crear_app(nucleo: NucleoASTRO | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(aplicacion: FastAPI) -> AsyncIterator[None]:
        if aplicacion.state.nucleo is None:
            aplicacion.state.nucleo = crear_nucleo()
        yield

    aplicacion = FastAPI(
        title="ASTRO Core",
        version="0.1",
        lifespan=lifespan,
    )
    aplicacion.state.nucleo = nucleo

    @aplicacion.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "astro-core"}

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
            return

    aplicacion.mount(
        "/static",
        StaticFiles(directory=RUTA_WEB),
        name="static",
    )

    return aplicacion


app = crear_app()
