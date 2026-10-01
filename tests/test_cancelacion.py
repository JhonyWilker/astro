from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.acceso import Acceso, Dispositivo
from core.api import crear_app
from core.chat import cargar_configuracion
from core.sesion import SesionASTRO
from core.turno import TurnoCancelado
import core.sesion as modulo_sesion
from tools.registro import RegistroHerramientas


def test_cancelar_turno_activo_conserva_solo_prefijo_confirmado(monkeypatch):
    def responder(*args):
        control = args[-1]
        control.emitido = "Primero. Segundo."
        args[4](control.emitido)
        assert control.evento.wait(5), "No llegó la cancelación"
        control.comprobar()

    monkeypatch.setattr(modulo_sesion, "responder_con_rutas", responder)
    nucleo = SimpleNamespace(
        configuracion=cargar_configuracion(),
        rutas_para_turno=lambda rapida=False: (),
        personalidad="Prueba",
        registro=RegistroHerramientas.descubrir(),
        registrar_fallo=lambda *args: None, registrar_exito=lambda *args: None,
    )
    sesion = SesionASTRO(nucleo)
    nucleo.nueva_sesion = lambda restringida=False: sesion
    token = "falso-token-para-prueba-de-cancelacion"
    acceso = Acceso([Dispositivo("pc", "jhony", token)])
    app = crear_app(nucleo, SimpleNamespace(), acceso)
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as cliente:
        with cliente.websocket_connect("/ws") as ws:
            identificador = ws.receive_json()["session"]
            ws.send_json({"type": "message", "text": "Explica"})
            assert ws.receive_json()["type"] == "delta"
            with cliente.websocket_connect("/ws") as segundo:
                assert segundo.receive_json()["session"] == identificador
                segundo.send_json({"type": "message", "text": "No pisar"})
                assert segundo.receive_json()["type"] == "busy"
                ws.send_json({"type": "ack", "characters": 8})
                ws.send_json({"type": "cancel"})
                assert ws.receive_json()["type"] == "cancelled"
                sincronizado = segundo.receive_json()
                assert sincronizado["history"][-1]["content"] == "Primero."
        with cliente.websocket_connect("/ws") as nuevo:
            assert nuevo.receive_json()["history"][-1]["content"] == "Primero."
    assert sesion.cantidad_turnos == 1


def test_cancelar_edicion_restaura_el_historial_anterior(monkeypatch):
    historial = [
        {"role": "user", "content": "Pregunta original"},
        {"role": "assistant", "content": "Respuesta original"},
        {"role": "user", "content": "Turno posterior"},
        {"role": "assistant", "content": "Respuesta posterior"},
    ]
    nucleo = SimpleNamespace(
        configuracion=cargar_configuracion(),
        rutas_para_turno=lambda rapida=False: (),
        personalidad="Prueba",
        registro=RegistroHerramientas.descubrir(),
        registrar_fallo=lambda *args: None, registrar_exito=lambda *args: None,
    )
    sesion = SesionASTRO(
        nucleo,
        historial=[dict(item) for item in historial],
        herramientas_por_turno=[(), ()],
    )

    def cancelar(*args):
        control = args[-1]
        control.emitido = "Respuesta corregida a medias"
        control.confirmar(10)
        raise TurnoCancelado()

    monkeypatch.setattr(modulo_sesion, "responder_con_rutas", cancelar)
    control = modulo_sesion.ControlTurno()
    with pytest.raises(TurnoCancelado):
        sesion.editar_turno(0, "Pregunta corregida", control=control)

    assert sesion.historial == historial
    assert sesion.herramientas_por_turno == [(), ()]
    assert not control.historial_actualizado
