import asyncio
import json

import pytest

from clients.voz import limpiar_para_voz, recibir_respuesta


class WebSocketFalso:
    def __init__(self, eventos):
        self.eventos = iter(eventos)
        self.enviados = []

    async def send(self, mensaje):
        self.enviados.append(json.loads(mensaje))

    async def recv(self):
        return json.dumps(next(self.eventos))


def test_recibir_respuesta_reune_streaming_y_uso() -> None:
    websocket = WebSocketFalso(
        [
            {"type": "delta", "text": "Hola, "},
            {"type": "delta", "text": "Jhony."},
            {
                "type": "done",
                "usage": [
                    {
                        "tokens": 100,
                        "coste_estimado_usd": 0.001,
                    },
                    {
                        "tokens": 20,
                        "coste_estimado_usd": 0.0002,
                    },
                ],
            },
        ]
    )
    fragmentos = []

    respuesta = asyncio.run(
        recibir_respuesta(
            websocket,
            "Hola",
            fragmentos.append,
        )
    )

    assert websocket.enviados == [
        {"type": "message", "text": "Hola"}
    ]
    assert fragmentos == ["Hola, ", "Jhony."]
    assert respuesta.texto == "Hola, Jhony."
    assert respuesta.peticiones == 2
    assert respuesta.tokens == 120
    assert respuesta.coste_usd == pytest.approx(0.0012)


def test_recibir_respuesta_publica_estados_de_herramienta() -> None:
    websocket = WebSocketFalso(
        [
            {"type": "state", "state": "executing", "tool": "calcular"},
            {"type": "state", "state": "thinking"},
            {"type": "delta", "text": "Resultado: 42"},
            {"type": "done", "usage": []},
        ]
    )
    estados = []

    respuesta = asyncio.run(
        recibir_respuesta(
            websocket,
            "Calcula 6 por 7",
            cambiar_estado=lambda estado, herramienta: estados.append(
                (estado, herramienta)
            ),
        )
    )

    assert estados == [
        ("executing", "calcular"),
        ("thinking", None),
    ]
    assert respuesta.texto == "Resultado: 42"


def test_recibir_respuesta_rechaza_un_estado_desconocido() -> None:
    websocket = WebSocketFalso(
        [{"type": "state", "state": "inventado"}]
    )

    with pytest.raises(RuntimeError, match="estado desconocido"):
        asyncio.run(recibir_respuesta(websocket, "Hola"))


def test_recibir_respuesta_propaga_error_controlado() -> None:
    websocket = WebSocketFalso(
        [{"type": "error", "message": "Servicio no disponible"}]
    )

    with pytest.raises(RuntimeError, match="Servicio no disponible"):
        asyncio.run(recibir_respuesta(websocket, "Hola"))


def test_limpiar_para_voz_elimina_markdown_basico() -> None:
    texto = limpiar_para_voz(
        "## **Resultado:** visita [ASTRO](https://example.com)."
    )

    assert texto == "Resultado: visita ASTRO."
