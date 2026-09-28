"""Control de acceso compartido por HTTP y WebSocket, cerrado por defecto."""

import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest, randbelow, token_urlsafe
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


@dataclass(frozen=True)
class DispositivoRegistrado:
    nombre: str
    usuario: str
    huella: str


@dataclass(frozen=True)
class VinculacionPendiente:
    nombre: str
    usuario: str
    caduca: float


class Acceso:
    def __init__(self, dispositivos=(), origenes=(), ruta_registro=None):
        self.dispositivos = tuple(dispositivos)
        self.origenes = frozenset(origenes)
        self.ruta_registro = Path(ruta_registro) if ruta_registro else None
        self.registrados = self._cargar_registrados()
        self.vinculaciones = {}
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
        ruta = os.getenv(
            "ASTRO_PAIRED_DEVICES_PATH",
            str(Path(__file__).resolve().parents[1] / "data" / "dispositivos-vinculados.json"),
        )
        return cls(dispositivos, os.getenv("ASTRO_ORIGENES", "").split(), ruta)

    def _cargar_registrados(self):
        if self.ruta_registro is None or not self.ruta_registro.exists():
            return []
        datos = json.loads(self.ruta_registro.read_text(encoding="utf-8"))
        if not isinstance(datos, list):
            raise ValueError("El registro de dispositivos debe ser una lista")
        try:
            return [DispositivoRegistrado(**item) for item in datos]
        except TypeError as error:
            raise ValueError("El registro de dispositivos no es válido") from error

    def _guardar_registrados(self, registrados):
        if self.ruta_registro is None:
            self.registrados = registrados
            return
        self.ruta_registro.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.ruta_registro.with_suffix(".tmp")
        datos = [
            {
                "nombre": item.nombre,
                "usuario": item.usuario,
                "huella": item.huella,
            }
            for item in registrados
        ]
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(self.ruta_registro)
        self.registrados = registrados

    def identificar(self, token):
        if not token or len(token) > 512:
            return None
        encontrado = None
        for dispositivo in self.dispositivos:
            if compare_digest(token.encode(), dispositivo.token.encode()):
                encontrado = dispositivo
        huella = sha256(token.encode()).hexdigest()
        for dispositivo in self.registrados:
            if compare_digest(huella, dispositivo.huella):
                encontrado = Dispositivo(
                    dispositivo.nombre,
                    dispositivo.usuario,
                    token,
                    False,
                )
        return encontrado

    def _limpiar_vinculaciones(self):
        ahora = monotonic()
        for codigo, vinculacion in list(self.vinculaciones.items()):
            if vinculacion.caduca <= ahora:
                del self.vinculaciones[codigo]

    def crear_vinculacion(self, nombre, usuario):
        nombre = " ".join(nombre.split())
        if not nombre or len(nombre) > 60 or any(ord(letra) < 32 for letra in nombre):
            raise ValueError("El nombre debe tener entre 1 y 60 caracteres")
        self._limpiar_vinculaciones()
        ocupados = {
            item.nombre.casefold()
            for item in (*self.dispositivos, *self.registrados)
        }
        ocupados.update(item.nombre.casefold() for item in self.vinculaciones.values())
        if nombre.casefold() in ocupados:
            raise ValueError("Ya existe un dispositivo con ese nombre")
        if len(self.vinculaciones) >= 10:
            raise ValueError("Hay demasiadas vinculaciones pendientes")
        while True:
            codigo = f"{randbelow(100_000_000):08d}"
            if codigo not in self.vinculaciones:
                break
        self.vinculaciones[codigo] = VinculacionPendiente(
            nombre,
            usuario,
            monotonic() + 300,
        )
        return f"{codigo[:4]} {codigo[4:]}", 300

    def reclamar_vinculacion(self, codigo, identidad):
        if not self.permitir(("vinculacion", identidad), 5, 300):
            raise PermissionError("Demasiados intentos de vinculación")
        normalizado = "".join(letra for letra in codigo if letra.isdigit())
        self._limpiar_vinculaciones()
        pendiente = self.vinculaciones.pop(normalizado, None)
        if pendiente is None:
            raise ValueError("El código no es válido o ha caducado")
        token = token_urlsafe(32)
        registrado = DispositivoRegistrado(
            pendiente.nombre,
            pendiente.usuario,
            sha256(token.encode()).hexdigest(),
        )
        self._guardar_registrados([*self.registrados, registrado])
        return Dispositivo(registrado.nombre, registrado.usuario, token, False)

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
        publico_estatico = ruta in {
            "/", "/health", "/manifest.webmanifest", "/service-worker.js",
        } or ruta.startswith("/static/")
        reclamo_publico = (
            tipo == "http"
            and ruta == "/auth/pair/claim"
            and scope.get("method") == "POST"
        )

        async def rechazar(estado):
            if tipo == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse(
                    {"detail": "Acceso rechazado"}, status_code=estado,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)

        if origen is not None and origen not in self.acceso.origenes:
            return await rechazar(403)
        if publico_estatico and tipo == "http":
            return await self.app(scope, receive, send)
        if not reclamo_publico:
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
            if (
                ruta.startswith("/ai/")
                or ruta in {"/push/test", "/auth/pairings"}
            ) and not dispositivo.administrador:
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
