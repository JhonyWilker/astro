"""Conversaciones compartidas entre conexiones del mismo usuario autenticado."""

import asyncio
from dataclasses import dataclass, field
from secrets import token_urlsafe
from time import monotonic


@dataclass
class Conversacion:
    sesion: object
    identificador: str = field(default_factory=lambda: token_urlsafe(24))
    bloqueo: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Cada valor es una función de envío protegida por el bloqueo propio de
    # esa conexión. Así dos dispositivos nunca escriben a la vez en el mismo
    # WebSocket al recibir una sincronización.
    conexiones: dict = field(default_factory=dict)
    ultimo_uso: float = field(default_factory=monotonic)
    publicado: list = field(default_factory=list)

    def historial(self):
        if self.bloqueo.locked():
            return [dict(item) for item in self.publicado]
        return [dict(item) for item in getattr(self.sesion, "historial", [])]


class Conversaciones:
    def __init__(self):
        self._usuarios = {}

    def obtener(self, usuario, nucleo, restringida=False):
        ahora = monotonic()
        for nombre, conversacion in list(self._usuarios.items()):
            if not conversacion.conexiones and not conversacion.bloqueo.locked() and ahora - conversacion.ultimo_uso > 86400:
                del self._usuarios[nombre]
        if usuario not in self._usuarios:
            if len(self._usuarios) >= 64:
                raise ValueError("Límite de conversaciones alcanzado")
            self._usuarios[usuario] = Conversacion(
                nucleo.nueva_sesion(restringida=restringida)
            )
        return self._usuarios[usuario]
