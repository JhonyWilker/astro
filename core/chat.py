from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json

import yaml
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
    ErrorLimiteHerramientas,
    ErrorRespuestaASTRO,
)
from core.proveedores import (
    ConfiguracionProveedor,
    crear_cliente_responses,
)
from core.uso import (
    RegistroUso,
    Tarifas,
    crear_informe_diario,
    crear_registro,
    guardar_registro,
    resumir_registro,
)
from tools.base import ContextoHerramienta, ErrorHerramienta
from tools.registro import RegistroHerramientas

RUTA_CONFIG = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
RUTA_PERSONALIDAD = (
    Path(__file__).resolve().parents[1] / "config" / "personality.md"
)

EmitirTexto = Callable[[str], None]


@dataclass(frozen=True)
class Configuracion:
    proveedor: ConfiguracionProveedor
    modelo: str
    idioma: str
    zona_horaria: str
    nivel_servicio: str
    timeout_segundos: float
    reintentos: int
    pasos_herramienta_maximos: int
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

    agente = datos.get("agente")
    if not isinstance(agente, dict):
        raise ValueError("Falta la sección 'agente' en config/config.yaml")

    proveedores = datos.get("proveedores")
    if not isinstance(proveedores, dict):
        raise ValueError("Falta la sección 'proveedores' en config/config.yaml")

    precios = datos.get("precios_usd_por_millon")
    if not isinstance(precios, dict):
        raise ValueError(
            "Falta la sección 'precios_usd_por_millon' en config/config.yaml"
        )

    proveedor_identificador = datos.get("proveedor")
    if (
        not isinstance(proveedor_identificador, str)
        or not proveedor_identificador.strip()
    ):
        raise ValueError("'proveedor' debe ser texto no vacío")
    proveedor_identificador = proveedor_identificador.strip()

    datos_proveedor = proveedores.get(proveedor_identificador)
    if not isinstance(datos_proveedor, dict):
        raise ValueError(
            f"El proveedor '{proveedor_identificador}' no está configurado"
        )

    campos_proveedor = {
        "nombre_visible": datos_proveedor.get("nombre_visible"),
        "base_url": datos_proveedor.get("base_url"),
        "clave_entorno": datos_proveedor.get("clave_entorno"),
    }
    for nombre, valor in campos_proveedor.items():
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(
                f"El campo '{nombre}' de '{proveedor_identificador}' "
                "debe ser texto no vacío"
            )
        campos_proveedor[nombre] = valor.strip()

    if not campos_proveedor["base_url"].startswith("https://"):
        raise ValueError(
            f"La URL de '{proveedor_identificador}' debe usar HTTPS"
        )

    modelo = datos.get("modelo")
    idioma = datos.get("idioma")
    zona_horaria = datos.get("zona_horaria")
    nivel_servicio = datos.get("nivel_servicio")
    tokens = limites.get("tokens_salida_maximos")
    turnos = limites.get("turnos_historial_maximos")
    timeout_segundos = api.get("timeout_segundos")
    reintentos = api.get("reintentos")
    pasos_herramienta_maximos = agente.get(
        "pasos_herramienta_maximos"
    )

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

    if (
        type(pasos_herramienta_maximos) is not int
        or not 1 <= pasos_herramienta_maximos <= 10
    ):
        raise ValueError(
            "'pasos_herramienta_maximos' debe ser un entero entre 1 y 10"
        )

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
        proveedor=ConfiguracionProveedor(
            identificador=proveedor_identificador,
            nombre_visible=campos_proveedor["nombre_visible"],
            base_url=campos_proveedor["base_url"],
            clave_entorno=campos_proveedor["clave_entorno"],
        ),
        modelo=modelo.strip(),
        idioma=idioma.strip(),
        zona_horaria=zona_horaria,
        nivel_servicio=nivel_servicio,
        timeout_segundos=float(timeout_segundos),
        reintentos=reintentos,
        pasos_herramienta_maximos=pasos_herramienta_maximos,
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
    return crear_cliente_responses(
        configuracion.proveedor,
        configuracion.timeout_segundos,
        configuracion.reintentos,
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


def explicar_error(
    error: Exception,
    proveedor: str = "OpenAI",
) -> str:
    if isinstance(error, ErrorLimiteHerramientas):
        return (
            "La tarea necesitó más pasos de herramientas de los permitidos. "
            "La detuve para evitar un bucle o gasto inesperado."
        )
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
            f"No puedo conectar con {proveedor}. Comprueba la conexión a internet "
            "y vuelve a intentarlo."
        )
    if isinstance(error, AuthenticationError):
        return f"La clave de {proveedor} no es válida o dejó de estar activa."
    if isinstance(error, PermissionDeniedError):
        return (
            f"La clave de {proveedor} no tiene permiso para realizar "
            "esta petición."
        )
    if isinstance(error, BadRequestError):
        return (
            f"{proveedor} rechazó la petición. "
            "Revisa el modelo y la configuración."
        )
    if isinstance(error, RateLimitError):
        if getattr(error, "code", None) in CODIGOS_LIMITE_PERMANENTE:
            return (
                f"Se alcanzó un límite de saldo, uso o gasto de {proveedor}. "
                "Necesita revisión en el panel."
            )
        return (
            "OpenAI está limitando temporalmente las peticiones. "
            "Espera un momento y vuelve a intentarlo."
        )
    if isinstance(error, InternalServerError):
        return (
            f"{proveedor} tiene un problema temporal. "
            "Ya agoté los reintentos configurados."
        )
    if isinstance(error, APIStatusError):
        return f"{proveedor} devolvió un error HTTP {error.status_code}."
    return f"Se produjo un error al comunicarse con {proveedor}."


def ejecutar_stream(
    cliente: OpenAI,
    configuracion: Configuracion,
    registro: RegistroHerramientas,
    instrucciones: str,
    entrada: list,
    emitir_texto: EmitirTexto | None = None,
) -> tuple[Response, str, RegistroUso]:
    inicio = perf_counter()

    eventos = cliente.responses.create(
        model=configuracion.modelo,
        instructions=instrucciones,
        input=entrada,
        max_output_tokens=configuracion.tokens_salida_maximos,
        service_tier=configuracion.nivel_servicio,
        tools=registro.definiciones_api(),
        parallel_tool_calls=False,
        stream=True,
    )
    fragmentos: list[str] = []
    respuesta_final = None

    for evento in eventos:
        if evento.type == "response.output_text.delta":
            if emitir_texto is not None:
                emitir_texto(evento.delta)
            fragmentos.append(evento.delta)
        elif evento.type == "response.completed":
            respuesta_final = evento.response
        elif evento.type in {"error", "response.failed", "response.incomplete"}:
            raise ErrorRespuestaASTRO()

    duracion = perf_counter() - inicio

    if respuesta_final is None or respuesta_final.usage is None:
        raise ErrorRespuestaASTRO()

    uso = respuesta_final.usage
    registro = crear_registro(
        proveedor=configuracion.proveedor.identificador,
        modelo=respuesta_final.model,
        servicio=respuesta_final.service_tier or configuracion.nivel_servicio,
        tokens_entrada=uso.input_tokens,
        tokens_entrada_cache=uso.input_tokens_details.cached_tokens or 0,
        tokens_escritura_cache=(
            uso.input_tokens_details.cache_write_tokens or 0
        ),
        tokens_salida=uso.output_tokens,
        tokens_razonamiento=(
            uso.output_tokens_details.reasoning_tokens or 0
        ),
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
    registro: RegistroHerramientas,
    emitir_texto: EmitirTexto | None = None,
) -> ResultadoRespuesta:
    instrucciones = (
        f"{personalidad}\n\n"
        f"Idioma habitual configurado: {configuracion.idioma}."
    )
    limite_mensajes = configuracion.turnos_historial_maximos * 2 - 1
    historial_limitado = historial[-limite_mensajes:]
    entrada_actual: list = [*historial_limitado]
    fragmentos_totales: list[str] = []
    registros: list[RegistroUso] = []
    pasos_herramienta = 0

    while True:
        respuesta, texto, registro_uso = ejecutar_stream(
            cliente,
            configuracion,
            registro,
            instrucciones,
            entrada_actual,
            emitir_texto,
        )
        fragmentos_totales.append(texto)
        registros.append(registro_uso)
        llamadas = [
            elemento
            for elemento in respuesta.output
            if elemento.type == "function_call"
        ]

        if not llamadas:
            return ResultadoRespuesta(
                texto="".join(fragmentos_totales),
                registros=tuple(registros),
            )

        if len(llamadas) != 1:
            raise ErrorRespuestaASTRO()

        if (
            pasos_herramienta
            >= configuracion.pasos_herramienta_maximos
        ):
            raise ErrorLimiteHerramientas()

        llamada = llamadas[0]
        try:
            argumentos = json.loads(llamada.arguments)
        except json.JSONDecodeError as error:
            raise ErrorRespuestaASTRO() from error

        if not isinstance(argumentos, dict):
            raise ErrorRespuestaASTRO()

        contexto = ContextoHerramienta(
            zona_horaria=configuracion.zona_horaria
        )
        try:
            resultado_herramienta = registro.ejecutar(
                llamada.name,
                argumentos,
                contexto,
            )
        except ErrorHerramienta as error:
            raise ErrorRespuestaASTRO() from error

        entrada_actual.extend(respuesta.output)
        entrada_actual.append(
            {
                "type": "function_call_output",
                "call_id": llamada.call_id,
                "output": json.dumps(
                    resultado_herramienta,
                    ensure_ascii=False,
                ),
            }
        )
        pasos_herramienta += 1


def main() -> None:
    from core.sesion import crear_nucleo

    nucleo = crear_nucleo()
    sesion = nucleo.nueva_sesion()

    def emitir_terminal(texto: str) -> None:
        print(texto, end="", flush=True)

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

        print("\nASTRO: ", end="", flush=True)
        try:
            resultado = sesion.preguntar(
                pregunta,
                emitir_terminal,
            )
        except (APIError, ErrorRespuestaASTRO) as error:
            mensaje = explicar_error(
                error,
                nucleo.configuracion.proveedor.nombre_visible,
            )
            print(f"\nASTRO: {mensaje}")
            continue
        print()
        for registro in resultado.registros:
            print(f"[{resumir_registro(registro)}]")


if __name__ == "__main__":
    main()
