from types import SimpleNamespace

from fastapi.testclient import TestClient

from core.api import crear_app


class SesionFalsa:
    def __init__(self) -> None:
        self.preguntas: list[str] = []

    def preguntar(self, pregunta: str, emitir_texto):
        self.preguntas.append(pregunta)
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
        )


class NucleoFalso:
    def __init__(self) -> None:
        self.sesion = SesionFalsa()

    def nueva_sesion(self) -> SesionFalsa:
        return self.sesion


def test_health() -> None:
    with TestClient(crear_app(NucleoFalso())) as cliente:
        respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "status": "ok",
        "service": "astro-core",
    }


def test_pagina_web() -> None:
    with TestClient(crear_app(NucleoFalso())) as cliente:
        respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "<title>ASTRO</title>" in respuesta.text
    assert 'rel="manifest"' in respuesta.text
    assert 'src="/static/app.js"' in respuesta.text


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
    assert "serviceWorker.register" in javascript.text
    assert estilos.status_code == 200
    assert icono.status_code == 200
    assert service_worker.status_code == 200
    assert service_worker.headers["service-worker-allowed"] == "/"


def test_websocket_transmite_respuesta() -> None:
    nucleo = NucleoFalso()
    with TestClient(crear_app(nucleo)) as cliente:
        with cliente.websocket_connect("/ws") as websocket:
            assert websocket.receive_json() == {"type": "ready"}
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
