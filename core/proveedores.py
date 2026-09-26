from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv
from openai import OpenAI

RUTA_ENV = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class ConfiguracionProveedor:
    identificador: str
    nombre_visible: str
    base_url: str
    clave_entorno: str


def crear_cliente_responses(
    proveedor: ConfiguracionProveedor,
    timeout_segundos: float,
    reintentos: int,
) -> OpenAI:
    load_dotenv(RUTA_ENV)
    clave_api = os.getenv(proveedor.clave_entorno)
    if not clave_api:
        raise RuntimeError(
            f"Falta {proveedor.clave_entorno} en el archivo .env "
            f"para usar {proveedor.nombre_visible}"
        )

    return OpenAI(
        api_key=clave_api,
        base_url=proveedor.base_url,
        timeout=timeout_segundos,
        max_retries=reintentos,
    )
