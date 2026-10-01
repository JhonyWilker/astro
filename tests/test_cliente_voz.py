import asyncio
import json

import pytest

from clients.voz import (
    comprobar_destinatario,
    confirmar_activacion,
    crear_argumentos,
    limpiar_para_voz,
    recibir_respuesta,
)


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


def test_recibir_respuesta_publica_expresion_sin_sumarla_al_texto() -> None:
    websocket = WebSocketFalso(
        [
            {
                "type": "voice_style",
                "direction": "deeply relieved, soft, quietly joyful",
            },
            {"type": "delta", "text": "Todo ha salido bien."},
            {"type": "done", "usage": []},
        ]
    )
    expresiones = []

    respuesta = asyncio.run(
        recibir_respuesta(
            websocket,
            "¿Qué ha pasado?",
            cambiar_expresion=expresiones.append,
        )
    )

    assert respuesta.texto == "Todo ha salido bien."
    assert expresiones == ["deeply relieved, soft, quietly joyful"]


def test_comprobar_destinatario_interpreta_respuesta_y_uso() -> None:
    websocket = WebSocketFalso([{
        "type": "direction",
        "addressed": False,
        "reason": "other_person",
        "usage": [{"tokens": 9, "coste_estimado_usd": 0.0003}],
    }])

    resultado = asyncio.run(comprobar_destinatario(
        websocket, "María, ven", "followup"
    ))

    assert websocket.enviados == [{
        "type": "classify_direction",
        "text": "María, ven",
        "origin": "followup",
    }]
    assert resultado.dirigida is False
    assert resultado.motivo == "other_person"
    assert resultado.tokens == 9


@pytest.mark.parametrize(
    "texto",
    ["Dime cuánto es dos más dos", "Sí", "Puedes repetirlo"],
)
def test_seguimiento_directo_se_resuelve_sin_red(texto: str) -> None:
    websocket = WebSocketFalso([])

    resultado = asyncio.run(comprobar_destinatario(
        websocket,
        texto,
        "followup",
    ))

    assert resultado.dirigida is True
    assert resultado.peticiones == 0
    assert websocket.enviados == []


def test_frase_ajena_explicita_se_descarta_sin_red() -> None:
    websocket = WebSocketFalso([])

    resultado = asyncio.run(comprobar_destinatario(
        websocket,
        "No te hablaba, era con María",
        "followup",
    ))

    assert resultado.dirigida is False
    assert resultado.motivo == "other_person"
    assert websocket.enviados == []


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


def test_seguimiento_predeterminado_ofrece_cinco_turnos_y_ocho_segundos() -> None:
    opciones = crear_argumentos().parse_args([])

    assert opciones.turnos_seguimiento == 5
    assert opciones.espera_seguimiento == pytest.approx(8.0)
    assert opciones.retardo_eco == 0
    assert opciones.interrumpir_con_voz is True


def test_interrupcion_por_voz_solo_se_desactiva_expresamente() -> None:
    opciones = crear_argumentos().parse_args(["--sin-interrumpir-con-voz"])

    assert opciones.interrumpir_con_voz is False


def test_activacion_confirmada_no_necesita_clasificacion() -> None:
    direccion = confirmar_activacion()

    assert direccion.dirigida is True
    assert direccion.peticiones == 0
