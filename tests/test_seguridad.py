import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.acceso import Acceso, Dispositivo
from core.api import crear_app
from core.conversaciones import Conversaciones
from core.turno import ControlTurno, TurnoCancelado
from tests.test_api import NucleoFalso, NotificacionesFalsas


TOKEN = "solo-pruebas-credencial-no-operativa-123456789"
ORIGEN = "https://astro.test"


def app_prueba(admin=True):
    return crear_app(NucleoFalso(), NotificacionesFalsas(), Acceso(
        [Dispositivo("pc", "jhony", TOKEN, admin)], [ORIGEN],
    ))


@pytest.mark.parametrize("ruta", ["/status", "/ai/settings", "/push/public-key"])
def test_http_requiere_credencial(ruta):
    with TestClient(app_prueba()) as cliente:
        assert cliente.get(ruta).status_code == 401


@pytest.mark.parametrize("headers", [{}, {"Authorization": f"Bearer {TOKEN}", "Origin": "https://maliciosa.test"}])
def test_ws_rechaza_anonimo_y_origen_ajeno(headers):
    with TestClient(app_prueba()) as cliente:
        with pytest.raises(WebSocketDisconnect):
            with cliente.websocket_connect("/ws", headers=headers):
                pytest.fail("Conexión no autorizada")


def test_cookie_segura_y_origen_obligatorio_para_mutaciones():
    with TestClient(app_prueba(), base_url=ORIGEN) as cliente:
        respuesta = cliente.post("/auth/login", headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGEN})
        assert respuesta.status_code == 200
        cookie = respuesta.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
        assert cliente.get("/status", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
        assert cliente.post("/push/test").status_code == 401
        assert cliente.post("/push/test", headers={"Origin": "https://ajena.test"}).status_code == 403


def test_limite_http_y_permisos_administrativos():
    with TestClient(app_prueba(False), headers={"Authorization": f"Bearer {TOKEN}"}) as cliente:
        assert cliente.get("/ai/settings").status_code == 403
        assert cliente.post("/push/subscribe", content=b"x" * 16385).status_code == 413


def test_esquema_bearer_no_depende_de_mayusculas():
    with TestClient(app_prueba(), headers={"Authorization": f"bearer {TOKEN}"}) as cliente:
        assert cliente.get("/status").status_code == 200


def test_configuracion_rechaza_tokens_duplicados(monkeypatch):
    repetido = "x" * 32
    monkeypatch.setenv(
        "ASTRO_DISPOSITIVOS",
        json.dumps([
            {"nombre": "uno", "usuario": "jhony", "token": repetido},
            {"nombre": "dos", "usuario": "jhony", "token": repetido},
        ]),
    )
    with pytest.raises(ValueError, match="no pueden repetirse"):
        Acceso.desde_entorno()


def test_ws_limite_de_frame():
    with TestClient(app_prueba(), headers={"Authorization": f"Bearer {TOKEN}"}) as cliente:
        with cliente.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_text("x" * 16385)
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code == 1009


def test_limite_de_frecuencia():
    acceso = Acceso()
    assert all(acceso.permitir("dispositivo", 3) for _ in range(3))
    assert not acceso.permitir("dispositivo", 3)


def test_conversacion_reutilizada_y_aislada_por_usuario():
    almacén = Conversaciones()
    nucleo = SimpleNamespace(nueva_sesion=lambda: SimpleNamespace(historial=[]))
    una = almacén.obtener("jhony", nucleo)
    una.sesion.historial.append({"role": "user", "content": "Privado"})
    assert almacén.obtener("jhony", nucleo) is una
    assert almacén.obtener("otro", nucleo).historial() == []


def test_ws_reconexion_conserva_identificador():
    with TestClient(app_prueba(), headers={"Authorization": f"Bearer {TOKEN}"}) as cliente:
        with cliente.websocket_connect("/ws") as ws:
            anterior = ws.receive_json()["session"]
        with cliente.websocket_connect("/ws") as ws:
            assert ws.receive_json()["session"] == anterior


def test_cancelacion_cierra_stream_y_limita_confirmaciones():
    cierres = []
    control = ControlTurno()
    control.vincular(SimpleNamespace(close=lambda: cierres.append(True)))
    control.emitido = "Primero. Segundo."
    control.confirmar(8)
    control.confirmar(1000)
    control.confirmar(-1)
    assert control.confirmado == 8
    control.cancelar()
    assert cierres == [True]
    with pytest.raises(TurnoCancelado):
        control.comprobar()
