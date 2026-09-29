from types import SimpleNamespace

from fastapi.testclient import TestClient as ClientePruebas

from core.api import crear_app as crear_app_real
from core.acceso import Acceso, Dispositivo


TOKEN_PRUEBA = "credencial-ficticia-exclusiva-de-pruebas"


def crear_app(*args, **kwargs):
    kwargs["acceso"] = Acceso([Dispositivo("prueba", "jhony", TOKEN_PRUEBA, True)], ["https://testserver"])
    return crear_app_real(*args, **kwargs)


def TestClient(app):
    return ClientePruebas(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})


class SesionFalsa:
    def __init__(self) -> None:
        self.preguntas: list[str] = []
        self.ediciones: list[tuple[int, str]] = []

    @property
    def cantidad_turnos(self) -> int:
        return len(self.preguntas)

    def preguntar(
        self,
        pregunta: str,
        emitir_texto,
        emitir_cambio=None,
        control=None,
        emitir_progreso=None,
    ):
        self.preguntas.append(pregunta)
        if pregunta == "Calcula":
            emitir_progreso("executing", "calcular")
            emitir_progreso("thinking", None)
        emitir_texto("Hola, ")
        emitir_texto("Jhony.")
        registro = SimpleNamespace(
            tokens_totales=12,
            duracion_segundos=0.25,
            coste_estimado_usd=0.001,
        )
        return SimpleNamespace(
            texto="Hola, Jhony.",
            registros=(registro,),
            proveedor_final="prueba",
            modelo_final="modelo-prueba",
            cambios_proveedor=(),
        )

    def editar_turno(
        self,
        indice: int,
        pregunta: str,
        emitir_texto,
        emitir_cambio=None,
        control=None,
        emitir_progreso=None,
    ):
        self.ediciones.append((indice, pregunta))
        return self.preguntar(
            pregunta,
            emitir_texto,
            emitir_cambio,
            control,
            emitir_progreso,
        )


class NucleoFalso:
    def __init__(self) -> None:
        self.sesion = SesionFalsa()
        self.configuracion = SimpleNamespace(
            proveedor=SimpleNamespace(nombre_visible="Proveedor prueba"),
            modelo="modelo-prueba",
        )
        self._estado_ia = {
            "active": "prueba",
            "provider": "prueba",
            "provider_name": "Proveedor prueba",
            "model": "modelo-prueba",
            "primary": "prueba",
            "fallback": "respaldo",
            "automatic": True,
            "retry_seconds": 120,
            "retry_in_seconds": 0,
            "degraded": False,
            "last_error": None,
            "providers": [
                {
                    "id": "prueba",
                    "name": "Proveedor prueba",
                    "model": "modelo-prueba",
                },
                {
                    "id": "respaldo",
                    "name": "Respaldo prueba",
                    "model": "modelo-respaldo",
                },
            ],
        }

    def nueva_sesion(self, restringida=False) -> SesionFalsa:
        return self.sesion

    def estado_ia(self) -> dict:
        return dict(self._estado_ia)

    def actualizar_ajustes_ia(self, ajustes) -> dict:
        proveedor = next(
            item
            for item in self._estado_ia["providers"]
            if item["id"] == ajustes.principal
        )
        self._estado_ia.update(
            {
                "active": ajustes.principal,
                "provider": ajustes.principal,
                "provider_name": proveedor["name"],
                "model": ajustes.modelos[ajustes.principal],
                "primary": ajustes.principal,
                "fallback": ajustes.respaldo,
                "automatic": ajustes.cambio_automatico,
                "retry_seconds": ajustes.reintento_principal_segundos,
            }
        )
        return self.estado_ia()


class NotificacionesFalsas:
    configurado = True
    clave_publica = "clave-publica"

    def __init__(self) -> None:
        self.suscripciones = []

    def contar(self) -> int:
        return len(self.suscripciones)

    def guardar(self, datos) -> int:
        self.suscripciones = [datos]
        return 1

    def eliminar(self, endpoint: str) -> int:
        self.suscripciones = [
            item
            for item in self.suscripciones
            if item["endpoint"] != endpoint
        ]
        return len(self.suscripciones)

    def enviar_prueba(self) -> tuple[int, int]:
        return len(self.suscripciones), 0


def test_health() -> None:
    with TestClient(crear_app(NucleoFalso())) as cliente:
        respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "status": "ok",
        "service": "astro-core",
    }


def test_panel_de_estado() -> None:
    with TestClient(
        crear_app(NucleoFalso(), NotificacionesFalsas())
    ) as cliente:
        respuesta = cliente.get("/status")

    assert respuesta.status_code == 200
    assert respuesta.json()["provider"] == "Proveedor prueba"
    assert respuesta.json()["model"] == "modelo-prueba"
    assert respuesta.json()["push"]["configured"] is True
    assert respuesta.json()["device"] == {
        "name": "prueba",
        "administrator": True,
        "role": "administrador",
    }


def test_ajustes_ia_exigen_token_y_se_actualizan() -> None:
    nucleo = NucleoFalso()
    with TestClient(crear_app(nucleo, NotificacionesFalsas())) as cliente:
        actuales = cliente.get("/ai/settings")
        datos = actuales.json()
        nuevos = {
            "principal": "respaldo",
            "respaldo": "prueba",
            "modelos": {
                "prueba": "modelo-prueba",
                "respaldo": "modelo-respaldo-2",
            },
            "cambio_automatico": False,
            "reintento_principal_segundos": 300,
        }
        sin_token = cliente.put("/ai/settings", json=nuevos)
        actualizado = cliente.put(
            "/ai/settings",
            json=nuevos,
            headers={"X-ASTRO-CSRF": datos["csrf_token"]},
        )

    assert actuales.status_code == 200
    assert sin_token.status_code == 403
    assert actualizado.status_code == 200
    assert actualizado.json()["primary"] == "respaldo"
    assert actualizado.json()["model"] == "modelo-respaldo-2"


def test_flujo_de_suscripcion_push() -> None:
    notificaciones = NotificacionesFalsas()
    suscripcion = {
        "endpoint": "https://push.example/dispositivo",
        "expirationTime": None,
        "keys": {"p256dh": "p" * 32, "auth": "a" * 16},
    }
    with TestClient(
        crear_app(NucleoFalso(), notificaciones)
    ) as cliente:
        assert cliente.get("/push/public-key").json() == {
            "public_key": "clave-publica"
        }
        alta = cliente.post("/push/subscribe", json=suscripcion)
        prueba = cliente.post("/push/test")
        baja = cliente.post(
            "/push/unsubscribe",
            json={"endpoint": suscripcion["endpoint"]},
        )

    assert alta.json() == {"subscribed": True, "subscriptions": 1}
    assert prueba.json() == {"sent": 1, "failed": 0}
    assert baja.json() == {"subscribed": False, "subscriptions": 0}


def test_pagina_web() -> None:
    with TestClient(crear_app(NucleoFalso())) as cliente:
        respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "<title>ASTRO</title>" in respuesta.text
    assert 'rel="manifest"' in respuesta.text
    assert 'src="/static/app.js?v=10"' in respuesta.text
    assert 'href="/static/app.css?v=10"' in respuesta.text


def test_manifiesto_pwa() -> None:
    with TestClient(crear_app(NucleoFalso())) as cliente:
        respuesta = cliente.get("/manifest.webmanifest")

    assert respuesta.status_code == 200
    assert respuesta.json()["name"] == "ASTRO — Asistente personal"
    assert respuesta.json()["display"] == "standalone"
    assert respuesta.json()["start_url"] == "/"


def test_recursos_pwa() -> None:
    with TestClient(crear_app(NucleoFalso())) as cliente:
        javascript = cliente.get("/static/app.js")
        estilos = cliente.get("/static/app.css")
        icono = cliente.get("/static/icon.svg")
        service_worker = cliente.get("/service-worker.js")

    assert javascript.status_code == 200
    assert "new WebSocket" in javascript.text
    assert 'type: "edit"' in javascript.text
    assert 'evento.type === "rewind"' in javascript.text
    assert '"/auth/pairings"' in javascript.text
    assert '"/auth/pair/claim"' in javascript.text
    assert '"/auth/devices"' in javascript.text
    assert 'method: "PATCH"' in javascript.text
    assert 'method: "DELETE"' in javascript.text
    assert "serviceWorker.register" in javascript.text
    assert 'addEventListener("push"' in service_worker.text
    assert "showNotification" in service_worker.text
    assert estilos.status_code == 200
    assert icono.status_code == 200
    assert service_worker.status_code == 200
    assert service_worker.headers["service-worker-allowed"] == "/"


def test_websocket_transmite_respuesta() -> None:
    nucleo = NucleoFalso()
    with TestClient(crear_app(nucleo)) as cliente:
        with cliente.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "ready"
            websocket.send_json(
                {"type": "message", "text": "Salúdame"}
            )
            assert websocket.receive_json() == {
                "type": "delta",
                "text": "Hola, ",
            }
            assert websocket.receive_json() == {
                "type": "delta",
                "text": "Jhony.",
            }
            terminado = websocket.receive_json()

    assert terminado["type"] == "done"
    assert terminado["usage"] == [
        {
            "tokens": 12,
            "segundos": 0.25,
            "coste_estimado_usd": 0.001,
        }
    ]
    assert nucleo.sesion.preguntas == ["Salúdame"]


def test_websocket_transmite_el_estado_real_de_una_herramienta() -> None:
    nucleo = NucleoFalso()
    with TestClient(crear_app(nucleo)) as cliente:
        with cliente.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "ready"
            websocket.send_json({"type": "message", "text": "Calcula"})

            assert websocket.receive_json() == {
                "type": "state",
                "state": "executing",
                "tool": "calcular",
            }
            assert websocket.receive_json() == {
                "type": "state",
                "state": "thinking",
            }


def test_websocket_edita_y_rebobina_antes_de_responder() -> None:
    nucleo = NucleoFalso()
    with TestClient(crear_app(nucleo)) as cliente:
        with cliente.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "ready"
            websocket.send_json(
                {"type": "edit", "turn": 0, "text": "Texto corregido"}
            )
            assert websocket.receive_json() == {
                "type": "rewind",
                "turn": 0,
                "text": "Texto corregido",
            }
            assert websocket.receive_json() == {
                "type": "delta",
                "text": "Hola, ",
            }
            assert websocket.receive_json() == {
                "type": "delta",
                "text": "Jhony.",
            }
            terminado = websocket.receive_json()

    assert terminado["type"] == "done"
    assert terminado["turn"] == 0
    assert nucleo.sesion.ediciones == [(0, "Texto corregido")]
