"""Evalúa un modelo alternativo sin cambiar la configuración de ASTRO."""

import json

from core.chat import cargar_configuracion
from core.proveedores import crear_cliente_responses
from tools.base import ContextoHerramienta
from tools.registro import RegistroHerramientas


MODELO = "google/gemini-3.8-flash"


def completar(cliente, registro, entrada):
    configuracion = cargar_configuracion()
    eventos = cliente.responses.create(
        model=MODELO,
        instructions=(
            "Prueba técnica de ASTRO. Usa siempre la herramienta calcular "
            "para cualquier operación y responde en español."
        ),
        input=entrada,
        max_output_tokens=300,
        reasoning={"effort": "low"},
        tools=registro.definiciones_api(),
        parallel_tool_calls=False,
        stream=True,
    )
    respuesta = None
    texto = []
    for evento in eventos:
        if evento.type == "response.output_text.delta":
            texto.append(evento.delta)
        elif evento.type == "response.completed":
            respuesta = evento.response
    if respuesta is None:
        raise RuntimeError("El modelo no completó la respuesta")
    return respuesta, "".join(texto), configuracion.zona_horaria


def main():
    configuracion = cargar_configuracion()
    proveedor = configuracion.proveedores["openrouter"]
    cliente = crear_cliente_responses(
        proveedor,
        configuracion.timeout_segundos,
        configuracion.reintentos,
    )
    registro = RegistroHerramientas.descubrir()
    entrada = [{"role": "user", "content": "¿Cuánto es 125 por 48?"}]
    primera, _, zona_horaria = completar(cliente, registro, entrada)
    llamadas = [item for item in primera.output if item.type == "function_call"]
    if len(llamadas) != 1 or llamadas[0].name != "calcular":
        raise RuntimeError("El modelo no solicitó la calculadora correctamente")
    llamada = llamadas[0]
    resultado = registro.ejecutar(
        llamada.name,
        json.loads(llamada.arguments),
        ContextoHerramienta(zona_horaria=zona_horaria),
    )
    entrada.extend(primera.output)
    entrada.append({
        "type": "function_call_output",
        "call_id": llamada.call_id,
        "output": json.dumps(resultado, ensure_ascii=False),
    })
    segunda, texto, _ = completar(cliente, registro, entrada)
    if "6000" not in texto:
        raise RuntimeError("La respuesta final no incorporó el resultado exacto")
    tokens = (primera.usage.total_tokens or 0) + (segunda.usage.total_tokens or 0)
    print(f"Compatibilidad: OK | modelo: {MODELO}")
    print(f"Herramienta: {llamada.name} | respuesta: {texto.strip()}")
    print(f"Peticiones: 2 | tokens: {tokens}")


if __name__ == "__main__":
    main()
