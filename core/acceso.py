"""Control de acceso compartido por HTTP y WebSocket, cerrado por defecto."""

import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from secrets import compare_digest
from time import monotonic
from pathlib import Path
from dotenv import load_dotenv

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse


@dataclass(frozen=True)
class Dispositivo:
    nombre: str
    usuario: str
    token: str
    administrador: bool = False


class Acceso:
    def __init__(self, dispositivos=(), origenes=()):
        self.dispositivos = tuple(dispositivos)
        self.origenes = frozenset(origenes)
        self.intentos = defaultdict(deque)
        self.conexiones = defaultdict(int)

    @classmethod
    def desde_entorno(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        load_dotenv(Path(__file__).resolve().parents[1] / ".env.acceso")
        datos = json.loads(os.getenv("ASTRO_DISPOSITIVOS", "[]"))
        if not isinstance(datos, list):
            raise ValueError("ASTRO_DISPOSITIVOS debe ser una lista")
        try:
            dispositivos = [Dispositivo(**item) for item in datos]
        except (TypeError, AttributeError) as error:
            raise ValueError("ASTRO_DISPOSITIVOS no es válido") from error
        if any(len(item.token) < 32 for item in dispositivos):
            raise ValueError("Los tokens de dispositivo necesitan 32 caracteres")
        if len({item.nombre for item in dispositivos}) != len(dispositivos):
            raise ValueError("Los nombres de dispositivo no pueden repetirse")
        if len({item.token for item in dispositivos}) != len(dispositivos):
            raise ValueError("Los tokens de dispositivo no pueden repetirse")
        return cls(dispositivos, os.getenv("ASTRO_ORIGENES", "").split())

    def identificar(self, token):
        if not token or len(token) > 512:
            return None
        encontrado = None
        for dispositivo in self.dispositivos:
            if compare_digest(token.encode(), dispositivo.token.encode()):
                encontrado = dispositivo
        return encontrado

    def permitir(self, clave, limite, ventana=60):
        ahora = monotonic()
        cola = self.intentos[clave]
        while cola and cola[0] <= ahora - ventana:
            cola.popleft()
        if len(cola) >= limite:
            return False
        cola.append(ahora)
        # Limitar también la memoria consumida por identidades no autenticadas.
        if len(self.intentos) > 2048:
            for antigua in list(self.intentos):
                if not self.intentos[antigua] or self.intentos[antigua][-1] <= ahora - ventana:
                    del self.intentos[antigua]
        return True


class MiddlewareAcceso:
    def __init__(self, app, acceso):
        self.app = app
        self.acceso = acceso

    async def __call__(self, scope, receive, send):
        tipo = scope["type"]
        if tipo not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        conexion = HTTPConnection(scope)
        cabeceras = Headers(scope=scope)
        origen = cabeceras.get("origin")
        ruta = scope["path"]
        publico = ruta in {
            "/", "/health", "/manifest.webmanifest", "/service-worker.js",
        } or ruta.startswith("/static/")

        async def rechazar(estado):
            if tipo == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse(
                    {"detail": "Acceso rechazado"}, status_code=estado,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)

        if publico and tipo == "http":
            return await self.app(scope, receive, send)
        if origen is not None and origen not in self.acceso.origenes:
            return await rechazar(403)
        autorizacion = cabeceras.get("authorization", "").split(" ", 1)
        token = (
            autorizacion[1]
            if len(autorizacion) == 2 and autorizacion[0].lower() == "bearer"
            else None
        )
        if token is None:
            # Los clientes sin Origin deben autenticarse explícitamente con Bearer.
            if origen is None and not (
                tipo == "http" and scope.get("method") in {"GET", "HEAD"}
                and cabeceras.get("sec-fetch-site") == "same-origin"
            ):
                return await rechazar(401)
            token = conexion.cookies.get("astro_acceso")
        dispositivo = self.acceso.identificar(token)
        if dispositivo is None:
            return await rechazar(401)
        if ruta.startswith("/ai/") or ruta == "/push/test":
            if not dispositivo.administrador:
                return await rechazar(403)
        if not self.acceso.permitir((dispositivo.nombre, "http"), 120):
            return await rechazar(429)
        scope.setdefault("state", {})["dispositivo"] = dispositivo
        if tipo == "websocket":
            if self.acceso.conexiones[dispositivo.nombre] >= 4:
                return await rechazar(429)
            self.acceso.conexiones[dispositivo.nombre] += 1
            try:
                return await self.app(scope, receive, send)
            finally:
                self.acceso.conexiones[dispositivo.nombre] -= 1
        # Leer con límite antes del parser JSON, incluso sin Content-Length.
        cuerpo = bytearray()
        while True:
            evento = await receive()
            if evento["type"] == "http.disconnect":
                return
            cuerpo.extend(evento.get("body", b""))
            if len(cuerpo) > 16384:
                return await rechazar(413)
            if not evento.get("more_body", False):
                break
        entregado = False

        async def recibir():
            nonlocal entregado
            if not entregado:
                entregado = True
                return {"type": "http.request", "body": bytes(cuerpo), "more_body": False}
            return await receive()

        async def enviar(evento):
            if evento["type"] == "http.response.start":
                evento["headers"] = [*evento.get("headers", []), (b"cache-control", b"no-store")]
            await send(evento)

        await self.app(scope, recibir, enviar)
