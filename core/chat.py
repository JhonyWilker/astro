from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
import os

import yaml
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from core.errores import (
    ErrorRespuestaASTRO,
    crear_registro_error,
    guardar_registro_error,
)
from core.uso import (
    RegistroUso,
    Tarifas,
    crear_informe_diario,
    crear_registro,
    guardar_registro,
    resumir_registro,
)

RUTA_ENV = Path(__file__).resolve().parents[1] / ".env"
RUTA_CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
RUTA_PERSONALIDAD = (
    Path(__file__).resolve().parents[1] / "config" / "personality.md"
)


@dataclass(frozen=True)
class Configuracion:
    modelo: str
    idioma: str
    nivel_servicio: str
    timeout_segundos: float
    reintentos: int
    tokens_salida_maximos: int
    turnos_historial_maximos: int
    tarifas: Tarifas


@dataclass(frozen=True)
class ResultadoRespuesta:
    texto: str
    registro: RegistroUso


def cargar_configuracion(ruta: Path = RUTA_CONFIG) -> Configuracion:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, dict):
        raise ValueError("config/config.yaml debe contener un objeto")

    limites = datos.get("limites")
    if not isinstance(limites, dict):
        raise ValueError("Falta la sección 'limites' en config/config.yaml")

    api = datos.get("api")
    if not isinstance(api, dict):
        raise ValueError("Falta la sección 'api' en config/config.yaml")

    precios = datos.get("precios_usd_por_millon")
    if not isinstance(precios, dict):
        raise ValueError(
            "Falta la sección 'precios_usd_por_millon' en config/config.yaml"
        )

    modelo = datos.get("modelo")
    idioma = datos.get("idioma")
    nivel_servicio = datos.get("nivel_servicio")
    tokens = limites.get("tokens_salida_maximos")
    turnos = limites.get("turnos_historial_maximos")
    timeout_segundos = api.get("timeout_segundos")
    reintentos = api.get("reintentos")

    for nombre, valor in {
        "modelo": modelo,
        "idioma": idioma,
        "nivel_servicio": nivel_servicio,
    }.items():
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"'{nombre}' debe ser texto no vacío")

    if nivel_servicio != "default":
        raise ValueError(
            "'nivel_servicio' debe ser 'default' para usar las tarifas configuradas"
        )

    for nombre, valor in {
        "tokens_salida_maximos": tokens,
        "turnos_historial_maximos": turnos,
    }.items():
        if type(valor) is not int or valor <= 0:
            raise ValueError(f"'{nombre}' debe ser un entero positivo")

    if (
        isinstance(timeout_segundos, bool)
        or not isinstance(timeout_segundos, (int, float))
        or timeout_segundos <= 0
    ):
        raise ValueError("'timeout_segundos' debe ser un número positivo")

    if type(reintentos) is not int or not 0 <= reintentos <= 5:
        raise ValueError("'reintentos' debe ser un entero entre 0 y 5")

    valores_precios = {
        "entrada": precios.get("entrada"),
        "entrada_cache": precios.get("entrada_cache"),
        "escritura_cache": precios.get("escritura_cache"),
        "salida": precios.get("salida"),
    }
    for nombre, valor in valores_precios.items():
        if (
            isinstance(valor, bool)
            or not isinstance(valor, (int, float))
            or valor < 0
        ):
            raise ValueError(f"El precio '{nombre}' debe ser un número no negativo")

    return Configuracion(
        modelo=modelo.strip(),
        idioma=idioma.strip(),
        nivel_servicio=nivel_servicio,
        timeout_segundos=float(timeout_segundos),
        reintentos=reintentos,
        tokens_salida_maximos=tokens,
        turnos_historial_maximos=turnos,
        tarifas=Tarifas(
            entrada_usd_millon=float(valores_precios["entrada"]),
            entrada_cache_usd_millon=float(valores_precios["entrada_cache"]),
            escritura_cache_usd_millon=float(
                valores_precios["escritura_cache"]
            ),
            salida_usd_millon=float(valores_precios["salida"]),
        ),
    )


def crear_cliente(configuracion: Configuracion) -> OpenAI:
    load_dotenv(RUTA_ENV)
    clave_api = os.getenv("OPENAI_API_KEY")
    if not clave_api:
        raise RuntimeError("Falta OPENAI_API_KEY en el archivo .env")
    return OpenAI(
        api_key=clave_api,
        timeout=configuracion.timeout_segundos,
        max_retries=configuracion.reintentos,
    )


def cargar_personalidad() -> str:
    personalidad = RUTA_PERSONALIDAD.read_text(encoding="utf-8").strip()
    if not personalidad:
        raise RuntimeError("El archivo config/personality.md está vacío")
    return personalidad


CODIGOS_LIMITE_PERMANENTE = {
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
}


def es_error_reintentable(error: Exception) -> bool:
    if isinstance(error, RateLimitError):
        return getattr(error, "code", None) not in CODIGOS_LIMITE_PERMANENTE
    return isinstance(
        error,
        (APITimeoutError, APIConnectionError, InternalServerError),
    )


def explicar_error(error: Exception) -> str:
    if isinstance(error, ErrorRespuestaASTRO):
        return (
            "La respuesta se interrumpió antes de terminar. "
            "No la repetiré automáticamente para evitar duplicarla."
        )
    if isinstance(error, APITimeoutError):
        return (
            "La respuesta tardó demasiado. Ya agoté los reintentos "
            "configurados; puedes volver a intentarlo."
        )
    if isinstance(error, APIConnectionError):
        return (
            "No puedo conectar con OpenAI. Comprueba la conexión a internet "
            "y vuelve a intentarlo."
        )
    if isinstance(error, AuthenticationError):
        return "La clave de OpenAI no es válida o dejó de estar activa."
    if isinstance(error, PermissionDeniedError):
        return "La clave de OpenAI no tiene permiso para realizar esta petición."
    if isinstance(error, BadRequestError):
        return (
            "OpenAI rechazó la petición. Revisa el modelo y la configuración."
        )
    if isinstance(error, RateLimitError):
        if getattr(error, "code", None) in CODIGOS_LIMITE_PERMANENTE:
            return (
                "Se alcanzó un límite de saldo, uso o gasto de OpenAI. "
                "Necesita revisión en el panel."
            )
        return (
            "OpenAI está limitando temporalmente las peticiones. "
            "Espera un momento y vuelve a intentarlo."
        )
    if isinstance(error, InternalServerError):
        return (
            "OpenAI tiene un problema temporal. "
            "Ya agoté los reintentos configurados."
        )
    if isinstance(error, APIStatusError):
        return f"OpenAI devolvió un error HTTP {error.status_code}."
    return "Se produjo un error al comunicarse con OpenAI."


def responder(
    cliente: OpenAI,
    historial: list[dict[str, str]],
    personalidad: str,
    configuracion: Configuracion,
) -> ResultadoRespuesta:
    instrucciones = (
        f"{personalidad}\n\n"
        f"Idioma habitual configurado: {configuracion.idioma}."
    )
    limite_mensajes = configuracion.turnos_historial_maximos * 2 - 1
    historial_limitado = historial[-limite_mensajes:]
    inicio = perf_counter()

    eventos = cliente.responses.create(
        model=configuracion.modelo,
        instructions=instrucciones,
        input=historial_limitado,
        max_output_tokens=configuracion.tokens_salida_maximos,
        service_tier=configuracion.nivel_servicio,
        stream=True,
    )
    fragmentos: list[str] = []
    respuesta_final = None

    for evento in eventos:
        if evento.type == "response.output_text.delta":
            print(evento.delta, end="", flush=True)
            fragmentos.append(evento.delta)
        elif evento.type == "response.completed":
            respuesta_final = evento.response
        elif evento.type in {"error", "response.failed", "response.incomplete"}:
            print()
            raise ErrorRespuestaASTRO()

    duracion = perf_counter() - inicio
    print()

    if respuesta_final is None or respuesta_final.usage is None:
        raise ErrorRespuestaASTRO()

    uso = respuesta_final.usage
    registro = crear_registro(
        modelo=respuesta_final.model,
        servicio=respuesta_final.service_tier or configuracion.nivel_servicio,
        tokens_entrada=uso.input_tokens,
        tokens_entrada_cache=uso.input_tokens_details.cached_tokens,
        tokens_escritura_cache=uso.input_tokens_details.cache_write_tokens,
        tokens_salida=uso.output_tokens,
        tokens_razonamiento=uso.output_tokens_details.reasoning_tokens,
        tokens_totales=uso.total_tokens,
        duracion_segundos=duracion,
        tarifas=configuracion.tarifas,
    )
    guardar_registro(registro)

    return ResultadoRespuesta(
        texto="".join(fragmentos),
        registro=registro,
    )


def main() -> None:
    configuracion = cargar_configuracion()
    cliente = crear_cliente(configuracion)
    personalidad = cargar_personalidad()
    historial: list[dict[str, str]] = []
    print("ASTRO: Escribe 'salir' para terminar la conversación.")

    while True:
        pregunta = input("\nJhony: ").strip()

        if pregunta.lower() == "salir":
            print("ASTRO: Hasta luego, Jhony.")
            print()
            print(crear_informe_diario())
            return

        if not pregunta:
            print("ASTRO: Escribe una pregunta para que pueda responder.")
            continue

        historial.append({"role": "user", "content": pregunta})
        print("\nASTRO: ", end="", flush=True)
        try:
            resultado = responder(
                cliente,
                historial,
                personalidad,
                configuracion,
            )
        except (APIError, ErrorRespuestaASTRO) as error:
            historial.pop()
            reintentable = es_error_reintentable(error)
            registro_error = crear_registro_error(error, reintentable)
            guardar_registro_error(registro_error)
            print(f"\nASTRO: {explicar_error(error)}")
            continue
        historial.append({"role": "assistant", "content": resultado.texto})
        print(f"[{resumir_registro(resultado.registro)}]")


if __name__ == "__main__":
    main()
