"""Ventana limitada de conversación después de una activación."""

from dataclasses import dataclass


@dataclass
class VentanaSeguimiento:
    limite: int = 5
    restantes: int = 0

    def __post_init__(self) -> None:
        if type(self.limite) is not int or not 1 <= self.limite <= 10:
            raise ValueError(
                "Los turnos de seguimiento deben estar entre 1 y 10"
            )
        if type(self.restantes) is not int or not 0 <= self.restantes <= self.limite:
            raise ValueError("El contador de seguimiento no es válido")

    @property
    def activa(self) -> bool:
        return self.restantes > 0

    def abrir(self) -> None:
        self.restantes = self.limite

    def consumir(self) -> int:
        if not self.activa:
            raise RuntimeError("La ventana de seguimiento está cerrada")
        self.restantes -= 1
        return self.restantes

    def cerrar(self) -> None:
        self.restantes = 0
