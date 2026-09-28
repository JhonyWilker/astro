"""Prueba roles y revocación desplegados sin imprimir credenciales."""

from argparse import ArgumentParser
from http.cookiejar import MozillaCookieJar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE = "https://astro-vps.tailbee6db.ts.net"
ORIGEN = "https://astro-vps.tailbee6db.ts.net"
NOMBRE_PRUEBA = "Prueba fase 28c"


def enviar(opener, ruta, datos=None, token=None, metodo=None):
    cabeceras = {"Origin": ORIGEN}
    if datos is not None:
        cabeceras["Content-Type"] = "application/json"
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    peticion = Request(
        BASE + ruta,
        data=(json.dumps(datos).encode() if datos is not None else None),
        headers=cabeceras,
        method=metodo or ("POST" if datos is not None else "GET"),
    )
    try:
        with opener.open(peticion, timeout=15) as respuesta:
            return respuesta.status, json.load(respuesta)
    except HTTPError as error:
        return error.code, json.load(error)


def token_administrador(raiz):
    dispositivos = json.loads(
        (raiz / "data" / "acceso-dispositivos.json").read_text(encoding="utf-8")
    )
    return next(
        item["token"] for item in dispositivos
        if item["nombre"] == "navegador-portatil"
    )


def preparar(raiz, cookies, identidad):
    token = token_administrador(raiz)
    jar = MozillaCookieJar(cookies)
    nuevo = build_opener(HTTPCookieProcessor(jar))
    administrador = build_opener()
    estado, creada = enviar(
        administrador,
        "/auth/pairings",
        {"nombre": NOMBRE_PRUEBA, "rol": "restringido"},
        token,
    )
    if estado != 200:
        raise SystemExit(f"No se creó la vinculación: HTTP {estado}")
    estado, reclamada = enviar(
        nuevo,
        "/auth/pair/claim",
        {"codigo": creada["code"]},
    )
    if estado != 200 or reclamada.get("role") != "restringido":
        raise SystemExit(f"No se reclamó como restringido: HTTP {estado}")
    estado_panel, _ = enviar(nuevo, "/auth/devices")
    if estado_panel != 403:
        raise SystemExit("El dispositivo restringido pudo administrar ASTRO")
    estado, inventario = enviar(administrador, "/auth/devices", token=token)
    if estado != 200:
        raise SystemExit(f"No se leyó el inventario: HTTP {estado}")
    dispositivo = next(
        item for item in inventario["devices"] if item["name"] == NOMBRE_PRUEBA
    )
    identidad.write_text(dispositivo["id"], encoding="utf-8")
    ruta = f"/auth/devices/{dispositivo['id']}"
    estado, _ = enviar(
        administrador,
        ruta,
        {"rol": "personal"},
        token,
        "PATCH",
    )
    estado_personal, datos_personales = enviar(nuevo, "/status")
    if estado != 200 or estado_personal != 200 or datos_personales["device"]["role"] != "personal":
        raise SystemExit("El cambio a personal no se aplicó")
    estado, _ = enviar(
        administrador,
        ruta,
        {"rol": "restringido"},
        token,
        "PATCH",
    )
    if estado != 200:
        raise SystemExit("El retorno a restringido no se aplicó")
    estado, _ = enviar(administrador, ruta, token=token, metodo="DELETE")
    if estado != 200:
        raise SystemExit("No se revocó el dispositivo")
    estado_revocado, _ = enviar(nuevo, "/status")
    if estado_revocado != 401:
        raise SystemExit("La credencial revocada continuó activa")
    jar.save(ignore_discard=True, ignore_expires=True)
    print("Restringido: OK | sin administración: OK | cambio de rol: OK | revocación: OK")


def verificar(raiz, cookies, identidad):
    jar = MozillaCookieJar(cookies)
    jar.load(ignore_discard=True, ignore_expires=True)
    nuevo = build_opener(HTTPCookieProcessor(jar))
    estado, _ = enviar(nuevo, "/status")
    if estado != 401:
        raise SystemExit("La revocación no sobrevivió al reinicio")
    token = token_administrador(raiz)
    estado, inventario = enviar(build_opener(), "/auth/devices", token=token)
    identificador = identidad.read_text(encoding="utf-8")
    dispositivo = next(
        item for item in inventario["devices"] if item["id"] == identificador
    )
    if estado != 200 or not dispositivo["revoked"]:
        raise SystemExit("El registro revocado no persistió")
    print("Revocación tras reinicio: OK")


def main():
    argumentos = ArgumentParser()
    argumentos.add_argument("accion", choices=["preparar", "verificar"])
    opciones = argumentos.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    cookies = raiz / "data" / "prueba-vinculacion.cookies"
    identidad = raiz / "data" / "prueba-vinculacion-id.txt"
    if opciones.accion == "preparar":
        preparar(raiz, cookies, identidad)
    else:
        verificar(raiz, cookies, identidad)


if __name__ == "__main__":
    main()
