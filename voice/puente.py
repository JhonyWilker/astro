"""Puente local de ASTRO: publica el estado de la voz por WebSocket en 127.0.0.1.

El cliente de voz es el servidor; la ventana de escritorio u otro proceso se conecta
cuando quiere. Si nadie escucha, o un receptor falla, la voz no se entera.
"""
import asyncio
import json
import os
import secrets
import threading
import time
from hmac import compare_digest
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

import websockets.asyncio.server as ws_server
from websockets.exceptions import ConnectionClosed

VERSION_PROTOCOLO = 1
RUTA_INFO = Path(__file__).resolve().parents[1] / "data" / "puente.json"
ORIGEN_PREDETERMINADO = "https://astro-vps.tailbee6db.ts.net"
HOSTS_PERMITIDOS = frozenset({"127.0.0.1", "localhost"})
MAXIMO_CLIENTES = 4
ESPERA_AUTENTICACION = 3.0
ESPERA_ENVIO = 1.0
MENSAJES_EN_COLA = 100
TAMANO_MAXIMO_ENTRADA = 4096
INTERVALO_NIVEL_SEGUNDOS = 0.1


def origen_configurado():
    """Devuelve solo esquema y autoridad del origen web configurado."""
    valor = (
        os.getenv("ASTRO_WEB_ORIGIN")
        or os.getenv("ASTRO_URL_BASE")
        or ORIGEN_PREDETERMINADO
    ).strip()
    partes = urlsplit(valor)
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        return ORIGEN_PREDETERMINADO
    return f"{partes.scheme}://{partes.netloc}"


class PuenteLocal:
    def __init__(
        self,
        ruta_info=RUTA_INFO,
        origenes=None,
        maximo_clientes=MAXIMO_CLIENTES,
        espera_autenticacion=ESPERA_AUTENTICACION,
        al_control_microfono=None,
    ):
        self.ruta_info = Path(ruta_info)
        self.origenes = frozenset(origenes or {origen_configurado()})
        self.maximo_clientes = maximo_clientes
        self.espera_autenticacion = espera_autenticacion
        self.al_control_microfono = al_control_microfono
        self.token = secrets.token_urlsafe(32)
        self.puerto = None
        self._bucle = None
        self._parar = None
        self._hilo = None
        self._listo = threading.Event()
        self._clientes = {}
        self._ultimo_estado = None
        self._ultimo_nivel = 0.0
        self._ultimo_nivel_publicado = 0.0

    # --- Ciclo de vida (se llama desde el hilo de la voz) ---

    def iniciar(self):
        """Arranca el servidor. Devuelve False, sin lanzar nada, si no pudo."""
        self._hilo = threading.Thread(target=self._ejecutar, name="puente-local", daemon=True)
        self._hilo.start()
        self._listo.wait(timeout=5)
        return self.puerto is not None

    def detener(self):
        try:
            if self._bucle is not None and self._parar is not None:
                self._bucle.call_soon_threadsafe(self._parar.set)
            if self._hilo is not None:
                self._hilo.join(timeout=3)
        except Exception:
            pass
        self._borrar_info()

    def _ejecutar(self):
        try:
            asyncio.run(self._principal())
        except Exception:
            self.puerto = None
        finally:
            self._listo.set()

    async def _principal(self):
        self._bucle = asyncio.get_running_loop()
        self._parar = asyncio.Event()
        async with ws_server.serve(
            self._atender,
            "127.0.0.1",
            0,
            process_request=self._comprobar_origen,
            max_size=TAMANO_MAXIMO_ENTRADA,
        ) as servidor:
            self.puerto = servidor.sockets[0].getsockname()[1]
            self._escribir_info()
            self._listo.set()
            await self._parar.wait()

    # --- Publicación (segura entre hilos, nunca lanza ni espera) ---

    def publicar(self, tipo, **datos):
        try:
            if self._bucle is None:
                return
            mensaje = {
                "v": VERSION_PROTOCOLO,
                "type": tipo,
                "ts": round(time.time() * 1000),
                **datos,
            }
            texto = json.dumps(mensaje, ensure_ascii=False)
            self._bucle.call_soon_threadsafe(self._repartir, tipo, mensaje, texto)
        except Exception:
            pass

    def publicar_estado(self, estado, detalle):
        """Gancho para IndicadorEstados.al_cambiar."""
        self.publicar("state", state=getattr(estado, "value", str(estado)), detail=detalle)

    def publicar_nivel(self, nivel):
        """Publica el nivel del micrófono sin saturar el puente ni la GUI."""
        try:
            normalizado = max(0.0, min(1.0, float(nivel)))
            self._ultimo_nivel = normalizado
            ahora = time.monotonic()
            if ahora - self._ultimo_nivel_publicado < INTERVALO_NIVEL_SEGUNDOS:
                return
            self._ultimo_nivel_publicado = ahora
            self.publicar("mic_level", level=round(normalizado, 3))
        except (TypeError, ValueError):
            return

    def _repartir(self, tipo, mensaje, texto):
        if tipo == "state":
            self._ultimo_estado = mensaje
        for conexion, cola in list(self._clientes.items()):
            try:
                cola.put_nowait(texto)
            except asyncio.QueueFull:
                self._clientes.pop(conexion, None)
                asyncio.ensure_future(conexion.close(1013, "Cliente demasiado lento"))

    # --- Conexiones ---

    def _comprobar_origen(self, conexion, peticion):
        origen = peticion.headers.get("Origin")
        host = (peticion.headers.get("Host") or "").rsplit(":", 1)[0]
        if (origen is not None and origen not in self.origenes) or host not in HOSTS_PERMITIDOS:
            return conexion.respond(HTTPStatus.FORBIDDEN, "No permitido\n")
        return None

    async def _atender(self, conexion):
        if len(self._clientes) >= self.maximo_clientes:
            await conexion.close(1008, "Demasiados clientes")
            return
        if not await self._autenticar(conexion):
            await conexion.close(1008, "No autorizado")
            return
        ultimo = self._ultimo_estado or {}
        cola = asyncio.Queue(maxsize=MENSAJES_EN_COLA)
        cola.put_nowait(json.dumps({
            "v": VERSION_PROTOCOLO,
            "type": "hello",
            "state": ultimo.get("state"),
            "detail": ultimo.get("detail"),
            "mic_level": round(self._ultimo_nivel, 3),
        }, ensure_ascii=False))
        self._clientes[conexion] = cola
        escritor = asyncio.create_task(self._escribir(conexion, cola))
        try:
            async for texto in conexion:
                self._procesar_orden(texto)
        except ConnectionClosed:
            pass
        finally:
            self._clientes.pop(conexion, None)
            escritor.cancel()

    def _procesar_orden(self, texto):
        try:
            datos = json.loads(texto)
            silenciado = datos.get("muted")
            if (
                isinstance(datos, dict)
                and datos.get("type") == "set_mic_muted"
                and isinstance(silenciado, bool)
                and self.al_control_microfono is not None
            ):
                self.al_control_microfono(silenciado)
        except (ValueError, TypeError, AttributeError):
            return

    async def _autenticar(self, conexion):
        try:
            primero = await asyncio.wait_for(conexion.recv(), self.espera_autenticacion)
            datos = json.loads(primero)
            if not isinstance(datos, dict):
                return False
            token = datos.get("token")
            return (
                datos.get("type") == "auth"
                and isinstance(token, str)
                and compare_digest(token.encode(), self.token.encode())
            )
        except (asyncio.TimeoutError, ValueError, TypeError, ConnectionClosed):
            return False

    async def _escribir(self, conexion, cola):
        try:
            while True:
                texto = await cola.get()
                await asyncio.wait_for(conexion.send(texto), ESPERA_ENVIO)
        except Exception:
            self._clientes.pop(conexion, None)
            await conexion.close()

    # --- Archivo con puerto y token (solo para procesos locales del usuario) ---

    def _escribir_info(self):
        self.ruta_info.parent.mkdir(parents=True, exist_ok=True)
        contenido = {
            "v": VERSION_PROTOCOLO,
            "port": self.puerto,
            "token": self.token,
            "pid": os.getpid(),
        }
        temporal = self.ruta_info.with_suffix(".tmp")
        temporal.write_text(json.dumps(contenido), encoding="utf-8")
        try:
            os.chmod(temporal, 0o600)
        except OSError:
            pass
        os.replace(temporal, self.ruta_info)

    def _borrar_info(self):
        try:
            datos = json.loads(self.ruta_info.read_text(encoding="utf-8"))
            if datos.get("pid") == os.getpid():
                self.ruta_info.unlink()
        except (OSError, ValueError):
            pass
