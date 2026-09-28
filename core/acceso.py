"""Control de acceso compartido por HTTP y WebSocket, cerrado por defecto."""

import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from secrets import compare_digest, randbelow, token_urlsafe
from time import monotonic

from dotenv import load_dotenv
from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse


ROL_ADMINISTRADOR = "administrador"
ROL_PERSONAL = "personal"
ROL_RESTRINGIDO = "restringido"
ROLES = frozenset({ROL_ADMINISTRADOR, ROL_PERSONAL, ROL_RESTRINGIDO})


def _identificador_inicial(nombre):
    return f"inicial-{sha256(nombre.encode()).hexdigest()[:16]}"


@dataclass(frozen=True)
class Dispositivo:
    nombre: str
    usuario: str
    token: str
    administrador: bool = False
    rol: str | None = None
    identificador: str | None = None
    origen: str = "inicial"

    def __post_init__(self):
        rol = self.rol or (
            ROL_ADMINISTRADOR if self.administrador else ROL_PERSONAL
        )
        if rol not in ROLES:
            raise ValueError(f"Rol de dispositivo no válido: {rol}")
        object.__setattr__(self, "rol", rol)
        object.__setattr__(self, "administrador", rol == ROL_ADMINISTRADOR)
        object.__setattr__(
            self,
            "identificador",
            self.identificador or _identificador_inicial(self.nombre),
        )


@dataclass(frozen=True)
class DispositivoRegistrado:
    nombre: str
    usuario: str
    huella: str
    rol: str = ROL_PERSONAL
    identificador: str | None = None
    revocado: bool = False

    def __post_init__(self):
        if self.rol not in ROLES:
            raise ValueError(f"Rol de dispositivo no válido: {self.rol}")
        object.__setattr__(
            self,
            "identificador",
            self.identificador or f"vinculado-{self.huella[:16]}",
        )


@dataclass(frozen=True)
class VinculacionPendiente:
    nombre: str
    usuario: str
    rol: str
    caduca: float


class Acceso:
    def __init__(self, dispositivos=(), origenes=(), ruta_registro=None):
        self.dispositivos = tuple(dispositivos)
        self.origenes = frozenset(origenes)
        self.ruta_registro = Path(ruta_registro) if ruta_registro else None
        self.registrados, self.ajustes_iniciales = self._cargar_registro()
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

    def _cargar_registro(self):
        if self.ruta_registro is None or not self.ruta_registro.exists():
            return [], {}
        datos = json.loads(self.ruta_registro.read_text(encoding="utf-8"))
        if isinstance(datos, list):
            vinculados = datos
            iniciales = {}
        elif isinstance(datos, dict) and datos.get("version") == 2:
            vinculados = datos.get("vinculados", [])
            iniciales = datos.get("iniciales", {})
        else:
            raise ValueError("El registro de dispositivos no es válido")
        if not isinstance(vinculados, list) or not isinstance(iniciales, dict):
            raise ValueError("El registro de dispositivos no es válido")
        try:
            registrados = [DispositivoRegistrado(**item) for item in vinculados]
        except (TypeError, ValueError) as error:
            raise ValueError("El registro de dispositivos no es válido") from error
        for identificador, ajuste in iniciales.items():
            if not isinstance(identificador, str) or not isinstance(ajuste, dict):
                raise ValueError("Los ajustes de dispositivos iniciales no son válidos")
            if ajuste.get("rol") not in ROLES or not isinstance(ajuste.get("usuario"), str):
                raise ValueError("Los ajustes de dispositivos iniciales no son válidos")
        return registrados, iniciales

    def _guardar_registro(self):
        if self.ruta_registro is None:
            return
        self.ruta_registro.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.ruta_registro.with_suffix(".tmp")
        vinculados = [
            {
                "identificador": item.identificador,
                "nombre": item.nombre,
                "usuario": item.usuario,
                "huella": item.huella,
                "rol": item.rol,
                "revocado": item.revocado,
            }
            for item in self.registrados
        ]
        datos = {
            "version": 2,
            "vinculados": vinculados,
            "iniciales": self.ajustes_iniciales,
        }
        temporal.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporal.replace(self.ruta_registro)

    def _dispositivos_iniciales(self):
        resultado = []
        for base in self.dispositivos:
            ajuste = self.ajustes_iniciales.get(base.identificador, {})
            resultado.append(Dispositivo(
                base.nombre,
                ajuste.get("usuario", base.usuario),
                base.token,
                rol=ajuste.get("rol", base.rol),
                identificador=base.identificador,
                origen="inicial",
            ))
        return resultado

    def _esta_revocado_inicial(self, dispositivo):
        return bool(
            self.ajustes_iniciales
            .get(dispositivo.identificador, {})
            .get("revocado", False)
        )

    def identificar(self, token):
        if not token or len(token) > 512:
            return None
        encontrado = None
        for dispositivo in self._dispositivos_iniciales():
            if (
                not self._esta_revocado_inicial(dispositivo)
                and compare_digest(token.encode(), dispositivo.token.encode())
            ):
                encontrado = dispositivo
        huella = sha256(token.encode()).hexdigest()
        for dispositivo in self.registrados:
            if not dispositivo.revocado and compare_digest(huella, dispositivo.huella):
                encontrado = Dispositivo(
                    dispositivo.nombre,
                    dispositivo.usuario,
                    token,
                    rol=dispositivo.rol,
                    identificador=dispositivo.identificador,
                    origen="vinculado",
                )
        return encontrado

    def listar_dispositivos(self, identificador_actual=None):
        resultado = []
        for dispositivo in self._dispositivos_iniciales():
            resultado.append({
                "id": dispositivo.identificador,
                "name": dispositivo.nombre,
                "role": dispositivo.rol,
                "source": dispositivo.origen,
                "revoked": self._esta_revocado_inicial(dispositivo),
                "current": dispositivo.identificador == identificador_actual,
            })
        for dispositivo in self.registrados:
            resultado.append({
                "id": dispositivo.identificador,
                "name": dispositivo.nombre,
                "role": dispositivo.rol,
                "source": "vinculado",
                "revoked": dispositivo.revocado,
                "current": dispositivo.identificador == identificador_actual,
            })
        return sorted(resultado, key=lambda item: (item["revoked"], item["name"].casefold()))

    def _buscar_inicial(self, identificador):
        return next(
            (item for item in self._dispositivos_iniciales() if item.identificador == identificador),
            None,
        )

    def cambiar_rol(self, identificador, rol, usuario_propietario, identificador_actual):
        if rol not in ROLES:
            raise ValueError("El rol no es válido")
        if identificador == identificador_actual:
            raise ValueError("No puedes cambiar el rol del dispositivo que estás usando")
        usuario = (
            f"restringido:{token_urlsafe(18)}"
            if rol == ROL_RESTRINGIDO
            else usuario_propietario
        )
        inicial = self._buscar_inicial(identificador)
        if inicial is not None:
            ajuste_anterior = self.ajustes_iniciales.get(identificador, {})
            if rol == ROL_RESTRINGIDO and ajuste_anterior.get("rol") == ROL_RESTRINGIDO:
                usuario = ajuste_anterior["usuario"]
            self.ajustes_iniciales[identificador] = {
                "rol": rol,
                "usuario": usuario,
                "revocado": False,
            }
            self._guardar_registro()
            return
        for indice, dispositivo in enumerate(self.registrados):
            if dispositivo.identificador != identificador:
                continue
            if rol == ROL_RESTRINGIDO and dispositivo.rol == ROL_RESTRINGIDO:
                usuario = dispositivo.usuario
            self.registrados[indice] = replace(
                dispositivo,
                usuario=usuario,
                rol=rol,
                revocado=False,
            )
            self._guardar_registro()
            return
        raise KeyError("Dispositivo no encontrado")

    def revocar(self, identificador, identificador_actual):
        if identificador == identificador_actual:
            raise ValueError("No puedes revocar el dispositivo que estás usando")
        inicial = self._buscar_inicial(identificador)
        if inicial is not None:
            ajuste = self.ajustes_iniciales.get(identificador, {})
            self.ajustes_iniciales[identificador] = {
                "rol": ajuste.get("rol", inicial.rol),
                "usuario": ajuste.get("usuario", inicial.usuario),
                "revocado": True,
            }
            self._guardar_registro()
            return
        for indice, dispositivo in enumerate(self.registrados):
            if dispositivo.identificador == identificador:
                self.registrados[indice] = replace(dispositivo, revocado=True)
                self._guardar_registro()
                return
        raise KeyError("Dispositivo no encontrado")

    def _limpiar_vinculaciones(self):
        ahora = monotonic()
        for codigo, vinculacion in list(self.vinculaciones.items()):
            if vinculacion.caduca <= ahora:
                del self.vinculaciones[codigo]

    def crear_vinculacion(self, nombre, usuario, rol=ROL_ADMINISTRADOR):
        nombre = " ".join(nombre.split())
        if not nombre or len(nombre) > 60 or any(ord(letra) < 32 for letra in nombre):
            raise ValueError("El nombre debe tener entre 1 y 60 caracteres")
        if rol not in ROLES:
            raise ValueError("El rol no es válido")
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
        usuario_dispositivo = (
            f"restringido:{token_urlsafe(18)}"
            if rol == ROL_RESTRINGIDO
            else usuario
        )
        self.vinculaciones[codigo] = VinculacionPendiente(
            nombre,
            usuario_dispositivo,
            rol,
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
            pendiente.rol,
            f"vinculado-{token_urlsafe(12)}",
        )
        self.registrados.append(registrado)
        self._guardar_registro()
        return Dispositivo(
            registrado.nombre,
            registrado.usuario,
            token,
            rol=registrado.rol,
            identificador=registrado.identificador,
            origen="vinculado",
        )

    def permitir(self, clave, limite, ventana=60):
        ahora = monotonic()
        cola = self.intentos[clave]
        while cola and cola[0] <= ahora - ventana:
            cola.popleft()
        if len(cola) >= limite:
            return False
        cola.append(ahora)
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
                if origen is None and not (
                    tipo == "http" and scope.get("method") in {"GET", "HEAD"}
                    and cabeceras.get("sec-fetch-site") == "same-origin"
                ):
                    return await rechazar(401)
                token = conexion.cookies.get("astro_acceso")
            dispositivo = self.acceso.identificar(token)
            if dispositivo is None:
                return await rechazar(401)
            ruta_administrativa = (
                ruta.startswith("/ai/")
                or ruta.startswith("/auth/devices")
                or ruta in {"/push/test", "/auth/pairings"}
            )
            if ruta_administrativa and not dispositivo.administrador:
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
