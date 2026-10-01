import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import keyring
import keyring.backend
import keyring.errors
import pytest

from gui import vinculacion
from gui.vinculacion import ErrorVinculacion

TOKEN_VALIDO = "token-de-prueba-123"


class ServidorFalso(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _responder(self, estado, cabeceras=(), cuerpo=b"{}"):
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        for nombre, valor in cabeceras:
            self.send_header(nombre, valor)
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        codigo = json.loads(self.rfile.read(largo))["codigo"]
        if codigo == "12345678":
            cookie = f"astro_acceso={TOKEN_VALIDO}; HttpOnly; Max-Age=2592000; Path=/; SameSite=strict; Secure"
            self._responder(200, [("Set-Cookie", cookie)])
        elif codigo == "99999999":
            self._responder(429)
        elif codigo == "11111111":
            self._responder(200)  # respuesta sin cookie
        else:
            self._responder(400)

    def do_GET(self):
        if self.headers.get("Authorization") == f"Bearer {TOKEN_VALIDO}":
            self._responder(200)
        elif self.headers.get("Authorization") == "Bearer fallo":
            self._responder(500)
        else:
            self._responder(401)


@pytest.fixture
def url_servidor():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), ServidorFalso)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{servidor.server_port}"
    servidor.shutdown()
    servidor.server_close()


class AlmacenEnMemoria(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.datos = {}

    def get_password(self, servicio, usuario):
        return self.datos.get((servicio, usuario))

    def set_password(self, servicio, usuario, clave):
        self.datos[(servicio, usuario)] = clave

    def delete_password(self, servicio, usuario):
        if (servicio, usuario) not in self.datos:
            raise keyring.errors.PasswordDeleteError("no existe")
        del self.datos[(servicio, usuario)]


@pytest.fixture
def almacen():
    anterior = keyring.get_keyring()
    falso = AlmacenEnMemoria()
    keyring.set_keyring(falso)
    yield falso
    keyring.set_keyring(anterior)


def test_canjear_codigo_valido_devuelve_token(url_servidor) -> None:
    assert vinculacion.canjear_codigo(" 12345678 ", url_servidor) == TOKEN_VALIDO


def test_canjear_codigo_incorrecto(url_servidor) -> None:
    with pytest.raises(ErrorVinculacion, match="incorrecto, caducado o ya usado"):
        vinculacion.canjear_codigo("00000000", url_servidor)


def test_canjear_codigo_con_demasiados_intentos(url_servidor) -> None:
    with pytest.raises(ErrorVinculacion, match="Demasiados intentos"):
        vinculacion.canjear_codigo("99999999", url_servidor)


def test_canjear_codigo_sin_cookie_falla(url_servidor) -> None:
    with pytest.raises(ErrorVinculacion, match="ningún token"):
        vinculacion.canjear_codigo("11111111", url_servidor)


def test_canjear_codigo_sin_conexion() -> None:
    with pytest.raises(ErrorVinculacion, match="Tailscale"):
        vinculacion.canjear_codigo("12345678", "http://127.0.0.1:9")


def test_guardar_leer_y_borrar_token(almacen) -> None:
    assert vinculacion.leer_token() is None
    vinculacion.guardar_token(TOKEN_VALIDO)
    assert vinculacion.leer_token() == TOKEN_VALIDO
    vinculacion.borrar_token()
    assert vinculacion.leer_token() is None
    vinculacion.borrar_token()  # borrar dos veces no falla


def test_comprobar_token_valido_revocado_y_dudoso(url_servidor) -> None:
    assert vinculacion.comprobar_token(TOKEN_VALIDO, url_servidor) is True
    assert vinculacion.comprobar_token("revocado", url_servidor) is False
    assert vinculacion.comprobar_token("fallo", url_servidor) is None


def test_sin_conexion_no_se_considera_revocado() -> None:
    assert vinculacion.comprobar_token(TOKEN_VALIDO, "http://127.0.0.1:9") is None


def test_url_base_se_puede_configurar_sin_tocar_codigo(monkeypatch) -> None:
    monkeypatch.setenv("ASTRO_URL_BASE", "https://astro.example.test/")
    assert vinculacion.url_base_configurada() == "https://astro.example.test"
