"""Silencio duro y persistente del micrófono local de ASTRO."""
import json
import os
from pathlib import Path
from threading import Event, Lock
from weakref import WeakSet


RUTA_ESTADO = Path(__file__).resolve().parents[1] / "data" / "gui" / "microfono.json"


class ControlMicrofono:
    def __init__(self, ruta=RUTA_ESTADO) -> None:
        self.ruta = Path(ruta)
        self._bloqueo = Lock()
        self._cancelaciones = WeakSet()
        self._silenciado = self._leer()
        self._activo = Event()
        if not self._silenciado:
            self._activo.set()

    @property
    def silenciado(self) -> bool:
        with self._bloqueo:
            return self._silenciado

    def nueva_cancelacion(self) -> Event:
        evento = Event()
        with self._bloqueo:
            self._cancelaciones.add(evento)
            if self._silenciado:
                evento.set()
        return evento

    def esperar_activo(self) -> None:
        self._activo.wait()

    def cambiar(self, silenciado: bool) -> bool:
        if not isinstance(silenciado, bool):
            raise TypeError("El estado del micrófono debe ser booleano")
        with self._bloqueo:
            if silenciado == self._silenciado:
                return False
            self._silenciado = silenciado
            if silenciado:
                self._activo.clear()
                for cancelacion in tuple(self._cancelaciones):
                    cancelacion.set()
            else:
                self._activo.set()
            self._guardar()
        return True

    def _leer(self) -> bool:
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            return datos.get("muted") is True
        except (OSError, ValueError, AttributeError):
            return False

    def _guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.ruta.with_suffix(".tmp")
        temporal.write_text(
            json.dumps({"muted": self._silenciado}),
            encoding="utf-8",
        )
        try:
            os.chmod(temporal, 0o600)
        except OSError:
            pass
        os.replace(temporal, self.ruta)

