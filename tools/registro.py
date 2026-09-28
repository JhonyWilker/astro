from importlib import import_module
from pkgutil import iter_modules

from tools import __path__ as rutas_herramientas
from tools.base import (
    ContextoHerramienta,
    ErrorHerramienta,
    Herramienta,
)

MODULOS_DE_INFRAESTRUCTURA = {"base", "registro"}


class RegistroHerramientas:
    def __init__(self, herramientas: list[Herramienta]) -> None:
        self._herramientas: dict[str, Herramienta] = {}
        for herramienta in herramientas:
            if herramienta.nombre in self._herramientas:
                raise ValueError(
                    f"Herramienta duplicada: {herramienta.nombre}"
                )
            self._herramientas[herramienta.nombre] = herramienta

    @classmethod
    def descubrir(cls) -> "RegistroHerramientas":
        herramientas: list[Herramienta] = []
        modulos = sorted(
            modulo.name
            for modulo in iter_modules(rutas_herramientas)
            if (
                not modulo.name.startswith("_")
                and modulo.name not in MODULOS_DE_INFRAESTRUCTURA
            )
        )
        for nombre_modulo in modulos:
            modulo = import_module(f"tools.{nombre_modulo}")
            herramienta = getattr(modulo, "HERRAMIENTA", None)
            if not isinstance(herramienta, Herramienta):
                raise ValueError(
                    f"tools/{nombre_modulo}.py no define HERRAMIENTA"
                )
            herramientas.append(herramienta)
        return cls(herramientas)

    def listar(self) -> tuple[Herramienta, ...]:
        return tuple(self._herramientas.values())

    def filtrar(self, nombres: set[str]) -> "RegistroHerramientas":
        return RegistroHerramientas([
            herramienta
            for nombre, herramienta in self._herramientas.items()
            if nombre in nombres
        ])

    def definiciones_api(self) -> list[dict[str, object]]:
        return [
            herramienta.definicion_api()
            for herramienta in self._herramientas.values()
        ]

    def ejecutar(
        self,
        nombre: str,
        argumentos: dict[str, object],
        contexto: ContextoHerramienta,
    ) -> dict[str, object]:
        herramienta = self._herramientas.get(nombre)
        if herramienta is None:
            raise ErrorHerramienta(
                f"Herramienta no registrada: {nombre}"
            )
        try:
            return herramienta.ejecutor(argumentos, contexto)
        except ErrorHerramienta as error:
            return {"error": str(error)}
