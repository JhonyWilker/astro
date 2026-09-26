from copy import deepcopy
from types import SimpleNamespace
import json

import pytest
from openai import APIConnectionError

import core.chat as chat
from core.errores import ErrorLimiteHerramientas
from core.uso import Tarifas, calcular_coste_estimado
from tools.registro import RegistroHerramientas


def crear_uso():
    return SimpleNamespace(
        input_tokens=10,
        input_tokens_details=SimpleNamespace(
            cached_tokens=0,
            cache_write_tokens=None,
        ),
        output_tokens=5,
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        total_tokens=15,
    )


def respuesta_con_llamada(
    nombre: str,
    argumentos: dict,
    numero: int,
):
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name=nombre,
                arguments=json.dumps(argumentos),
                call_id=f"call_{numero}",
            )
        ],
        usage=crear_uso(),
        model="modelo-prueba",
        service_tier="default",
    )


def respuesta_final():
    return SimpleNamespace(
        output=[SimpleNamespace(type="message")],
        usage=crear_uso(),
        model="modelo-prueba",
        service_tier="default",
    )


class APIFalsa:
    def __init__(self, respuestas: list) -> None:
        self.respuestas = list(respuestas)
        self.llamadas: list[dict] = []

    def create(self, **opciones):
        self.llamadas.append(deepcopy(opciones))
        respuesta = self.respuestas.pop(0)
        eventos = []
        if not any(
            elemento.type == "function_call"
            for elemento in respuesta.output
        ):
            eventos.append(
                SimpleNamespace(
                    type="response.output_text.delta",
                    delta="Resultado final: 4072.",
                )
            )
        eventos.append(
            SimpleNamespace(
                type="response.completed",
                response=respuesta,
            )
        )
        return iter(eventos)


def test_calcular_coste_estimado() -> None:
    tarifas = Tarifas(
        entrada_usd_millon=10,
        entrada_cache_usd_millon=1,
        escritura_cache_usd_millon=12.5,
        salida_usd_millon=50,
    )

    coste = calcular_coste_estimado(
        tokens_entrada=1000,
        tokens_entrada_cache=200,
        tokens_escritura_cache=100,
        tokens_salida=50,
        tarifas=tarifas,
    )

    assert coste == pytest.approx(0.01095)


def test_explicar_limite_herramientas() -> None:
    mensaje = chat.explicar_error(ErrorLimiteHerramientas())

    assert "evitar un bucle" in mensaje
    assert "gasto inesperado" in mensaje


def test_error_de_conexion_nombra_el_proveedor_activo() -> None:
    error = APIConnectionError(
        request=SimpleNamespace(
            method="POST",
            url="https://openrouter.ai/api/v1/responses",
        )
    )

    mensaje = chat.explicar_error(error, "OpenRouter")

    assert "conectar con OpenRouter" in mensaje


def test_bucle_agente_encadena_tres_herramientas(
    monkeypatch,
    capsys,
) -> None:
    api = APIFalsa(
        [
            respuesta_con_llamada("obtener_fecha_hora", {}, 1),
            respuesta_con_llamada(
                "calcular",
                {"expresion": "2026 + 10"},
                2,
            ),
            respuesta_con_llamada(
                "calcular",
                {"expresion": "2036 * 2"},
                3,
            ),
            respuesta_final(),
        ]
    )
    monkeypatch.setattr(chat, "guardar_registro", lambda registro: None)

    resultado = chat.responder(
        SimpleNamespace(responses=api),
        [{"role": "user", "content": "Tarea de tres pasos"}],
        "Personalidad de prueba",
        chat.cargar_configuracion(),
        RegistroHerramientas.descubrir(),
    )

    capsys.readouterr()
    assert resultado.texto == "Resultado final: 4072."
    assert len(resultado.registros) == 4
    assert all(
        registro.proveedor == "openai"
        for registro in resultado.registros
    )
    assert all(
        registro.tokens_escritura_cache == 0
        for registro in resultado.registros
    )
    assert len(api.llamadas) == 4
    salida_final = json.loads(
        api.llamadas[-1]["input"][-1]["output"]
    )
    assert salida_final["resultado_exacto"] == "4072"
