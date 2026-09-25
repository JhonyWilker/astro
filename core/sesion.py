from collections.abc import Callable
from dataclasses import dataclass, field

from openai import APIError, OpenAI

from core.chat import (
    Configuracion,
    ResultadoRespuesta,
    cargar_configuracion,
    cargar_personalidad,
    crear_cliente,
    es_error_reintentable,
    responder,
)
from core.errores import (
    ErrorRespuestaASTRO,
    crear_registro_error,
    guardar_registro_error,
)
from tools.registro import RegistroHerramientas

EmitirTexto = Callable[[str], None]


@dataclass(frozen=True)
class NucleoASTRO:
    configuracion: Configuracion
    personalidad: str
    registro: RegistroHerramientas

    def nueva_sesion(self) -> "SesionASTRO":
        return SesionASTRO(
            cliente=crear_cliente(self.configuracion),
            configuracion=self.configuracion,
            personalidad=self.personalidad,
            registro=self.registro,
        )


@dataclass
class SesionASTRO:
    cliente: OpenAI
    configuracion: Configuracion
    personalidad: str
    registro: RegistroHerramientas
    historial: list[dict[str, str]] = field(default_factory=list)

    def preguntar(
        self,
        pregunta: str,
        emitir_texto: EmitirTexto | None = None,
    ) -> ResultadoRespuesta:
        pregunta = pregunta.strip()
        if not pregunta:
            raise ValueError("La pregunta no puede estar vacía")

        self.historial.append({"role": "user", "content": pregunta})
        try:
            resultado = responder(
                self.cliente,
                self.historial,
                self.personalidad,
                self.configuracion,
                self.registro,
                emitir_texto,
            )
        except (APIError, ErrorRespuestaASTRO) as error:
            self.historial.pop()
            guardar_registro_error(
                crear_registro_error(
                    error,
                    es_error_reintentable(error),
                )
            )
            raise

        self.historial.append(
            {"role": "assistant", "content": resultado.texto}
        )
        return resultado


def crear_nucleo() -> NucleoASTRO:
    return NucleoASTRO(
        configuracion=cargar_configuracion(),
        personalidad=cargar_personalidad(),
        registro=RegistroHerramientas.descubrir(),
    )
