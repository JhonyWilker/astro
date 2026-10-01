"""Vinculación del PC como dispositivo de ASTRO.

Canjea el código de un solo uso de la fase 28b, guarda el token en el almacén de
credenciales de Windows y comprueba si el servidor sigue aceptándolo.
"""
import json
import urllib.error
import urllib.request
from http.cookies import CookieError, SimpleCookie

import keyring
import keyring.errors

URL_BASE = "https://astro-vps.tailbee6db.ts.net"
NOMBRE_COOKIE = "astro_acceso"
SERVICIO = "ASTRO"
USUARIO = "dispositivo-pc"
ESPERA_SEGUNDOS = 10


class ErrorVinculacion(Exception):
    """Fallo al vincular; el mensaje está pensado para mostrarse a Jhony."""


def canjear_codigo(codigo, url_base=URL_BASE):
    """Envía el código al servidor y devuelve el token del dispositivo."""
    cuerpo = json.dumps({"codigo": codigo.strip()}).encode()
    peticion = urllib.request.Request(
        f"{url_base}/auth/pair/claim",
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=ESPERA_SEGUNDOS) as respuesta:
            cabeceras = respuesta.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise ErrorVinculacion(
                "Demasiados intentos. Espera unos minutos y genera un código nuevo."
            ) from error
        if error.code in (400, 422):
            raise ErrorVinculacion("Código incorrecto, caducado o ya usado.") from error
        raise ErrorVinculacion(f"El servidor rechazó la vinculación ({error.code}).") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ErrorVinculacion(
            "No se pudo conectar con ASTRO. ¿Está Tailscale activado?"
        ) from error

    token = _extraer_token(cabeceras)
    if token is None:
        raise ErrorVinculacion("El servidor no devolvió ningún token.")
    return token


def _extraer_token(cabeceras_cookie):
    for cabecera in cabeceras_cookie:
        galleta = SimpleCookie()
        try:
            galleta.load(cabecera)
        except CookieError:
            continue
        if NOMBRE_COOKIE in galleta and galleta[NOMBRE_COOKIE].value:
            return galleta[NOMBRE_COOKIE].value
    return None


def guardar_token(token):
    keyring.set_password(SERVICIO, USUARIO, token)


def leer_token():
    try:
        return keyring.get_password(SERVICIO, USUARIO)
    except keyring.errors.KeyringError:
        return None


def borrar_token():
    try:
        keyring.delete_password(SERVICIO, USUARIO)
    except keyring.errors.PasswordDeleteError:
        pass


def comprobar_token(token, url_base=URL_BASE):
    """True si sigue válido, False si el servidor lo rechaza, None si no se pudo saber."""
    peticion = urllib.request.Request(
        f"{url_base}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=ESPERA_SEGUNDOS):
            return True
    except urllib.error.HTTPError as error:
        return False if error.code == 401 else None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
