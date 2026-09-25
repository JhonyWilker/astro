import os
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()
cliente = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
respuesta = cliente.responses.create(
    model=os.getenv("OPENAI_MODEL", "gpt-6-astra"),
    input="Responde exactamente: Puerta del bloque 0 superada.",
)
print(respuesta.output_text)
