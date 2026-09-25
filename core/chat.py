from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
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
from openai.types.responses import Response

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
from tools.calculadora import (
    DEFINICION_HERRAMIENTA as DEFINICION_CALCULADORA,
    NOMBRE_HERRAMIENTA as NOMBRE_CALCULADORA,
    ErrorCalculo,
    calcular,
)
from tools.fecha_hora import (
    DEFINICION_HERRAMIENTA as DEFINICION_FECHA_HORA,
    NOMBRE_HERRAMIENTA as NOMBRE_FECHA_HORA,
    obtener_fecha_hora,
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
    zona_horaria: str
    nivel_servicio: str
    timeout_segundos: float
    reintentos: int
    tokens_salida_maximos: int
    turnos_historial_maximos: int
    tarifas: Tarifas


@dataclass(frozen=True)
class ResultadoRespuesta:
    texto: str
    registros: tuple[RegistroUso, ...]


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
    zona_horaria = datos.get("zona_horaria")
    nivel_servicio = datos.get("nivel_servicio")
    tokens = limites.get("tokens_salida_maximos")
    turnos = limites.get("turnos_historial_maximos")
    timeout_segundos = api.get("timeout_segundos")
    reintentos = api.get("reintentos")

    for nombre, valor in {
        "modelo": modelo,
        "idioma": idioma,
        "zona_horaria": zona_horaria,
        "nivel_servicio": nivel_servicio,
    }.items():
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"'{nombre}' debe ser texto no vacío")

    if nivel_servicio != "default":
        raise ValueError(
            "'nivel_servicio' debe ser 'default' para usar las tarifas configuradas"
        )

    zona_horaria = zona_horaria.strip()
    try:
        ZoneInfo(zona_horaria)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            f"'zona_horaria' no es válida: {zona_horaria}"
        ) from error

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
        zona_horaria=zona_horaria,
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


def ejecutar_stream(
    cliente: OpenAI,
    configuracion: Configuracion,
    instrucciones: str,
    entrada: list,
) -> tuple[Response, str, RegistroUso]:
    inicio = perf_counter()

    eventos = cliente.responses.create(
        model=configuracion.modelo,
        instructions=instrucciones,
        input=entrada,
        max_output_tokens=configuracion.tokens_salida_maximos,
        service_tier=configuracion.nivel_servicio,
        tools=[DEFINICION_FECHA_HORA, DEFINICION_CALCULADORA],
        parallel_tool_calls=False,
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

    return respuesta_final, "".join(fragmentos), registro


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
    respuesta, texto_inicial, registro_inicial = ejecutar_stream(
        cliente,
        configuracion,
        instrucciones,
        historial_limitado,
    )
    llamadas = [
        elemento
        for elemento in respuesta.output
        if elemento.type == "function_call"
    ]

    if not llamadas:
        print()
        return ResultadoRespuesta(
            texto=texto_inicial,
            registros=(registro_inicial,),
        )

    if len(llamadas) != 1:
        print()
        raise ErrorRespuestaASTRO()

    llamada = llamadas[0]
    try:
        argumentos = json.loads(llamada.arguments)
    except json.JSONDecodeError as error:
        print()
        raise ErrorRespuestaASTRO() from error

    if llamada.name == NOMBRE_FECHA_HORA:
        if argumentos != {}:
            print()
            raise ErrorRespuestaASTRO()
        resultado_herramienta = obtener_fecha_hora(
            configuracion.zona_horaria
        )
    elif llamada.name == NOMBRE_CALCULADORA:
        if (
            not isinstance(argumentos, dict)
            or set(argumentos) != {"expresion"}
            or not isinstance(argumentos["expresion"], str)
        ):
            print()
            raise ErrorRespuestaASTRO()
        try:
            resultado_herramienta = calcular(argumentos["expresion"])
        except ErrorCalculo as error:
            resultado_herramienta = {"error": str(error)}
    else:
        print()
        raise ErrorRespuestaASTRO()
    entrada_continuacion = [
        *historial_limitado,
        *respuesta.output,
        {
            "type": "function_call_output",
            "call_id": llamada.call_id,
            "output": json.dumps(
                resultado_herramienta,
                ensure_ascii=False,
            ),
        },
    ]
    respuesta_final, texto_final, registro_final = ejecutar_stream(
        cliente,
        configuracion,
        instrucciones,
        entrada_continuacion,
    )

    if any(
        elemento.type == "function_call"
        for elemento in respuesta_final.output
    ):
        print()
        raise ErrorRespuestaASTRO()

    print()
    return ResultadoRespuesta(
        texto=texto_inicial + texto_final,
        registros=(registro_inicial, registro_final),
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
        for registro in resultado.registros:
            print(f"[{resumir_registro(registro)}]")


if __name__ == "__main__":
    main()
