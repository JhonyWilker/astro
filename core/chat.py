from pathlib import Path
import os

from dotenv import load_dotenv
from openai import OpenAI

RUTA_ENV = Path(__file__).resolve().parents[1] / ".env"


def crear_cliente() -> OpenAI:
    load_dotenv(RUTA_ENV)
    clave_api = os.getenv("OPENAI_API_KEY")
    if not clave_api:
        raise RuntimeError("Falta OPENAI_API_KEY en el archivo .env")
    return OpenAI(api_key=clave_api)


def responder(
    cliente: OpenAI,
    historial: list[dict[str, str]],
) -> str:
    modelo = os.getenv("OPENAI_MODEL", "gpt-6-astra")
    respuesta = cliente.responses.create(
        model=modelo,
        input=historial,
    )
    return respuesta.output_text


def main() -> None:
    cliente = crear_cliente()
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
        respuesta = responder(cliente, historial)
        historial.append({"role": "assistant", "content": respuesta})
        print(f"\nASTRO: {respuesta}")


if __name__ == "__main__":
    main()
