from dataclasses import dataclass
from pathlib import Path
import os

import yaml
from dotenv import load_dotenv
from openai import OpenAI

RUTA_ENV = Path(__file__).resolve().parents[1] / ".env"
RUTA_CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
RUTA_PERSONALIDAD = (
    Path(__file__).resolve().parents[1] / "config" / "personality.md"
)


@dataclass(frozen=True)
class Configuracion:
    modelo: str
    idioma: str
    tokens_salida_maximos: int
    turnos_historial_maximos: int


def cargar_configuracion(ruta: Path = RUTA_CONFIG) -> Configuracion:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, dict):
        raise ValueError("config/config.yaml debe contener un objeto")

    limites = datos.get("limites")
    if not isinstance(limites, dict):
        raise ValueError("Falta la sección 'limites' en config/config.yaml")

    modelo = datos.get("modelo")
    idioma = datos.get("idioma")
    tokens = limites.get("tokens_salida_maximos")
    turnos = limites.get("turnos_historial_maximos")

    for nombre, valor in {"modelo": modelo, "idioma": idioma}.items():
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"'{nombre}' debe ser texto no vacío")

    for nombre, valor in {
        "tokens_salida_maximos": tokens,
        "turnos_historial_maximos": turnos,
    }.items():
        if type(valor) is not int or valor <= 0:
            raise ValueError(f"'{nombre}' debe ser un entero positivo")

    return Configuracion(
        modelo=modelo.strip(),
        idioma=idioma.strip(),
        tokens_salida_maximos=tokens,
        turnos_historial_maximos=turnos,
    )


def crear_cliente() -> OpenAI:
    load_dotenv(RUTA_ENV)
    clave_api = os.getenv("OPENAI_API_KEY")
    if not clave_api:
        raise RuntimeError("Falta OPENAI_API_KEY en el archivo .env")
    return OpenAI(api_key=clave_api)


def cargar_personalidad() -> str:
    personalidad = RUTA_PERSONALIDAD.read_text(encoding="utf-8").strip()
    if not personalidad:
        raise RuntimeError("El archivo config/personality.md está vacío")
    return personalidad


def responder(
    cliente: OpenAI,
    historial: list[dict[str, str]],
    personalidad: str,
    configuracion: Configuracion,
) -> str:
    instrucciones = (
        f"{personalidad}\n\n"
        f"Idioma habitual configurado: {configuracion.idioma}."
    )
    limite_mensajes = configuracion.turnos_historial_maximos * 2 - 1
    historial_limitado = historial[-limite_mensajes:]

    eventos = cliente.responses.create(
        model=configuracion.modelo,
        instructions=instrucciones,
        input=historial_limitado,
        max_output_tokens=configuracion.tokens_salida_maximos,
        stream=True,
    )
    fragmentos: list[str] = []

    for evento in eventos:
        if evento.type == "response.output_text.delta":
            print(evento.delta, end="", flush=True)
            fragmentos.append(evento.delta)

    print()
    return "".join(fragmentos)


def main() -> None:
    configuracion = cargar_configuracion()
    cliente = crear_cliente()
    personalidad = cargar_personalidad()
    historial: list[dict[str, str]] = []
    print("ASTRO: Escribe 'salir' para terminar la conversación.")

    while True:
        pregunta = input("\nJhony: ").strip()

        if pregunta.lower() == "salir":
            print("ASTRO: Hasta luego, Jhony.")
            return

        if not pregunta:
            print("ASTRO: Escribe una pregunta para que pueda responder.")
            continue

        historial.append({"role": "user", "content": pregunta})
        print("\nASTRO: ", end="", flush=True)
        respuesta = responder(
            cliente,
            historial,
            personalidad,
            configuracion,
        )
        historial.append({"role": "assistant", "content": respuesta})


if __name__ == "__main__":
    main()
