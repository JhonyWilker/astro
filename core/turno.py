"""Cancelación cooperativa y cierre del stream activo del proveedor."""

from threading import Event, Lock


class TurnoCancelado(Exception):
    pass


class ControlTurno:
    def __init__(self):
        self.evento = Event()
        self._lock = Lock()
        self._stream = None
        self.emitido = ""
        self.confirmado = 0
        self.herramientas = []
        self.generacion_completa = False
        self.historial_actualizado = False

    def comprobar(self):
        if self.evento.is_set():
            raise TurnoCancelado()

    def vincular(self, stream):
        with self._lock:
            self._stream = stream
        if self.evento.is_set():
            cerrar = getattr(stream, "close", None)
            if cerrar:
                cerrar()
        self.comprobar()

    def cancelar(self):
        self.evento.set()
        with self._lock:
            stream = self._stream
        cerrar = getattr(stream, "close", None)
        if cerrar:
            try:
                cerrar()
            except Exception:
                pass

    def confirmar(self, longitud):
        if type(longitud) is int and self.confirmado <= longitud <= len(self.emitido):
            self.confirmado = longitud
