from pathlib import Path
import os

from dotenv import load_dotenv
from openai import OpenAI

RUTA_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(RUTA_ENV)

clave_api = os.getenv("OPENAI_API_KEY")
if not clave_api:
    raise RuntimeError("Falta OPENAI_API_KEY en el archivo .env")

modelo = os.getenv("OPENAI_MODEL", "gpt-6-astra")
cliente = OpenAI(api_key=clave_api)

respuesta = cliente.responses.create(
    model=modelo,
    input="Responde exactamente: ASTRO conectado correctamente.",
)

print(respuesta.output_text)
