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


def responder(pregunta: str) -> str:
    cliente = crear_cliente()
    modelo = os.getenv("OPENAI_MODEL", "gpt-6-astra")
    respuesta = cliente.responses.create(
        model=modelo,
        input=pregunta,
    )
    return respuesta.output_text


def main() -> None:
    pregunta = input("Jhony: ").strip()
    if not pregunta:
        print("ASTRO: Escribe una pregunta para que pueda responder.")
        return
    respuesta = responder(pregunta)
    print(f"\nASTRO: {respuesta}")


if __name__ == "__main__":
    main()
