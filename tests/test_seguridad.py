import asyncio
import base64
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.acceso import Acceso, Dispositivo
from core.api import crear_app
from core.conversaciones import Conversaciones
from core.sesion import NucleoASTRO
from core.turno import ControlTurno, TurnoCancelado
from tools.registro import RegistroHerramientas
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


def test_vinculacion_por_codigo_es_unica_persistente_y_sin_token(tmp_path):
    ruta = tmp_path / "dispositivos.json"
    acceso = Acceso(
        [Dispositivo("administrador", "jhony", TOKEN, True)],
        [ORIGEN],
        ruta,
    )
    app = crear_app(NucleoFalso(), NotificacionesFalsas(), acceso)
    with TestClient(
        app,
        base_url=ORIGEN,
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGEN},
    ) as administrador:
        creada = administrador.post(
            "/auth/pairings",
            json={"nombre": "Tablet nueva"},
        )
    assert creada.status_code == 200
    datos = creada.json()
    assert len(datos["code"].replace(" ", "")) == 8
    assert datos["expires_in_seconds"] == 300
    assert datos["qr_data_uri"].startswith("data:image/svg+xml;base64,")
    svg = base64.b64decode(datos["qr_data_uri"].split(",", 1)[1]).decode()
    assert svg.startswith("<svg")
    assert datos["pairing_url"].startswith(f"{ORIGEN}/#vincular=")
    assert "?" not in datos["pairing_url"]

    with TestClient(
        app,
        base_url=ORIGEN,
        headers={"Origin": ORIGEN},
    ) as nuevo:
        reclamada = nuevo.post(
            "/auth/pair/claim",
            json={"codigo": datos["code"]},
        )
        assert reclamada.status_code == 200
        token_nuevo = nuevo.cookies.get("astro_acceso")
        estado = nuevo.get("/status")
        repetida = nuevo.post(
            "/auth/pair/claim",
            json={"codigo": datos["code"]},
        )

    assert estado.status_code == 200
    assert estado.json()["device"] == {
        "name": "Tablet nueva",
        "administrator": True,
        "role": "administrador",
    }
    assert repetida.status_code == 400
    assert token_nuevo not in ruta.read_text(encoding="utf-8")
    reiniciado = Acceso(
        [Dispositivo("administrador", "jhony", TOKEN, True)],
        [ORIGEN],
        ruta,
    )
    recuperado = reiniciado.identificar(token_nuevo)
    assert recuperado.nombre == "Tablet nueva"
    assert recuperado.administrador


@pytest.mark.parametrize(
    ("rol", "es_administrador", "comparte_usuario"),
    [
        ("administrador", True, True),
        ("personal", False, True),
        ("restringido", False, False),
    ],
)
def test_roles_definen_permiso_e_identidad(
    tmp_path,
    rol,
    es_administrador,
    comparte_usuario,
):
    acceso = Acceso(ruta_registro=tmp_path / "dispositivos.json")
    codigo, _ = acceso.crear_vinculacion("Nuevo", "jhony", rol)
    dispositivo = acceso.reclamar_vinculacion(codigo, f"prueba-{rol}")

    assert dispositivo.rol == rol
    assert dispositivo.administrador is es_administrador
    assert (dispositivo.usuario == "jhony") is comparte_usuario


def test_administracion_cambia_aisla_reactiva_y_revoca(tmp_path):
    ruta = tmp_path / "dispositivos.json"
    token_secundario = "credencial-secundaria-ficticia-1234567890"
    acceso = Acceso(
        [
            Dispositivo("actual", "jhony", TOKEN, True),
            Dispositivo("secundario", "jhony", token_secundario),
        ],
        [ORIGEN],
        ruta,
    )
    app = crear_app(NucleoFalso(), NotificacionesFalsas(), acceso)
    with TestClient(
        app,
        base_url=ORIGEN,
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGEN},
    ) as administrador:
        inventario = administrador.get("/auth/devices")
        dispositivos = inventario.json()["devices"]
        secundario = next(item for item in dispositivos if item["name"] == "secundario")
        actual = next(item for item in dispositivos if item["current"])
        restringido = administrador.patch(
            f"/auth/devices/{secundario['id']}",
            json={"rol": "restringido"},
        )
        autorrol = administrador.patch(
            f"/auth/devices/{actual['id']}",
            json={"rol": "personal"},
        )
        autorrevocacion = administrador.delete(f"/auth/devices/{actual['id']}")

    assert inventario.status_code == 200
    assert all(
        not {"token", "huella", "usuario"}.intersection(item)
        for item in dispositivos
    )
    assert restringido.status_code == 200
    aislado = acceso.identificar(token_secundario)
    assert aislado.rol == "restringido"
    assert aislado.usuario != "jhony"
    assert autorrol.status_code == 400
    assert autorrevocacion.status_code == 400

    with TestClient(
        app,
        base_url=ORIGEN,
        headers={"Authorization": f"Bearer {token_secundario}", "Origin": ORIGEN},
    ) as limitado:
        assert limitado.get("/auth/devices").status_code == 403

    with TestClient(
        app,
        base_url=ORIGEN,
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGEN},
    ) as administrador:
        assert administrador.patch(
            f"/auth/devices/{secundario['id']}",
            json={"rol": "personal"},
        ).status_code == 200
        assert acceso.identificar(token_secundario).usuario == "jhony"
        assert administrador.delete(f"/auth/devices/{secundario['id']}").status_code == 200

    assert acceso.identificar(token_secundario) is None
    reiniciado = Acceso(
        [
            Dispositivo("actual", "jhony", TOKEN, True),
            Dispositivo("secundario", "jhony", token_secundario),
        ],
        [ORIGEN],
        ruta,
    )
    assert reiniciado.identificar(token_secundario) is None


def test_cambio_de_rol_cierra_socket_con_identidad_anterior(tmp_path):
    token_secundario = "credencial-secundaria-para-socket-123456789"
    acceso = Acceso(
        [
            Dispositivo("actual", "jhony", TOKEN, True),
            Dispositivo("secundario", "jhony", token_secundario),
        ],
        [ORIGEN],
        tmp_path / "dispositivos.json",
    )
    app = crear_app(NucleoFalso(), NotificacionesFalsas(), acceso)
    secundario = acceso.identificar(token_secundario)
    with TestClient(
        app,
        headers={"Authorization": f"Bearer {token_secundario}"},
    ) as cliente:
        with cliente.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "ready"
            acceso.cambiar_rol(
                secundario.identificador,
                "restringido",
                "jhony",
                "otro-administrador",
            )
            websocket.send_json({"type": "message", "text": "Privado"})
            with pytest.raises(WebSocketDisconnect) as error:
                websocket.receive_json()
            assert error.value.code == 1008


def test_sesion_restringida_usa_personalidad_neutra_y_herramientas_seguras():
    nucleo = SimpleNamespace(
        personalidad_restringida="No conoces datos de Jhony.",
        registro=RegistroHerramientas.descubrir(),
    )
    sesion = NucleoASTRO.nueva_sesion(nucleo, restringida=True)

    assert sesion.personalidad == "No conoces datos de Jhony."
    assert {item.nombre for item in sesion.registro.listar()} == {
        "calcular",
        "obtener_fecha_hora",
    }


def test_dispositivo_normal_no_puede_crear_vinculaciones():
    app = app_prueba(False)
    with TestClient(
        app,
        base_url=ORIGEN,
        headers={"Authorization": f"Bearer {TOKEN}", "Origin": ORIGEN},
    ) as cliente:
        respuesta = cliente.post(
            "/auth/pairings",
            json={"nombre": "No permitido"},
        )
    assert respuesta.status_code == 403


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
    modos = []
    nucleo = SimpleNamespace(nueva_sesion=lambda restringida=False: (
        modos.append(restringida) or SimpleNamespace(historial=[])
    ))
    una = almacén.obtener("jhony", nucleo)
    una.sesion.historial.append({"role": "user", "content": "Privado"})
    assert almacén.obtener("jhony", nucleo) is una
    assert almacén.obtener("otro", nucleo, restringida=True).historial() == []
    assert modos == [False, True]


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
