from dataclasses import dataclass
from enum import StrEnum
from typing import Callable


class Riesgo(StrEnum):
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"


class ErrorHerramienta(ValueError):
    pass


@dataclass(frozen=True)
class ContextoHerramienta:
    zona_horaria: str


EjecutorHerramienta = Callable[
    [dict[str, object], ContextoHerramienta],
    dict[str, object],
]


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict[str, object]
    riesgo: Riesgo
    ejecutor: EjecutorHerramienta

    def definicion_api(self) -> dict[str, object]:
        return {
            "type": "function",
            "name": self.nombre,
            "description": self.descripcion,
            "parameters": self.parametros,
            "strict": True,
        }
