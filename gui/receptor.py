"""Receptor no bloqueante del puente local del nodo de voz."""
import asyncio
import json
from queue import Empty, Queue
import threading

import websockets.asyncio.client as ws_client
from PySide6.QtCore import QObject, Signal
from websockets.exceptions import WebSocketException

from gui.monitor import RUTA_INFO, leer_info


class ReceptorPuente(QObject):
    evento = Signal(object)
    conexion = Signal(bool)

    def __init__(self, ruta_info=RUTA_INFO, espera_reintento=1.0):
        super().__init__()
        self.ruta_info = ruta_info
        self.espera_reintento = espera_reintento
        self._parar = threading.Event()
        self._hilo = None
        self._conectado = None
        self._ordenes = Queue(maxsize=8)

    def establecer_microfono(self, silenciado: bool) -> None:
        if not isinstance(silenciado, bool):
            raise TypeError("El estado del micrófono debe ser booleano")
        try:
            self._ordenes.put_nowait({
                "type": "set_mic_muted",
                "muted": silenciado,
            })
        except Exception:
            return

    def iniciar(self) -> None:
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._parar.clear()
        self._hilo = threading.Thread(
            target=self._ejecutar,
            name="gui-puente-voz",
            daemon=True,
        )
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)

    def _cambiar_conexion(self, conectado: bool) -> None:
        if conectado != self._conectado:
            self._conectado = conectado
            self.conexion.emit(conectado)

    def _ejecutar(self) -> None:
        asyncio.run(self._escuchar())

    async def _esperar(self) -> None:
        await asyncio.to_thread(self._parar.wait, self.espera_reintento)

    async def _escuchar(self) -> None:
        while not self._parar.is_set():
            info = leer_info(self.ruta_info)
            if info is None:
                self._cambiar_conexion(False)
                await self._esperar()
                continue
            puerto, token = info
            try:
                async with ws_client.connect(
                    f"ws://127.0.0.1:{puerto}",
                    open_timeout=2.0,
                ) as conexion:
                    await conexion.send(json.dumps({
                        "type": "auth",
                        "token": token,
                    }))
                    self._cambiar_conexion(True)
                    while not self._parar.is_set():
                        try:
                            orden = self._ordenes.get_nowait()
                        except Empty:
                            orden = None
                        if orden is not None:
                            try:
                                await conexion.send(json.dumps(orden))
                            except Exception:
                                self._ordenes.put_nowait(orden)
                                raise
                        try:
                            mensaje = await asyncio.wait_for(
                                conexion.recv(),
                                timeout=0.05,
                            )
                        except asyncio.TimeoutError:
                            continue
                        evento = json.loads(mensaje)
                        if isinstance(evento, dict):
                            self.evento.emit(evento)
            except (OSError, ValueError, WebSocketException):
                pass
            self._cambiar_conexion(False)
            await self._esperar()
