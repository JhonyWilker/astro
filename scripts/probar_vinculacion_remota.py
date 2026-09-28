"""Prueba la vinculación desplegada sin imprimir códigos ni credenciales."""

from argparse import ArgumentParser
from http.cookiejar import MozillaCookieJar
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE = "https://astro-vps.tailbee6db.ts.net"
ORIGEN = "https://astro-vps.tailbee6db.ts.net"


def enviar(opener, ruta, datos=None, token=None):
    cabeceras = {"Origin": ORIGEN}
    if datos is not None:
        cabeceras["Content-Type"] = "application/json"
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    peticion = Request(
        BASE + ruta,
        data=(json.dumps(datos).encode() if datos is not None else None),
        headers=cabeceras,
        method="POST" if datos is not None else "GET",
    )
    try:
        with opener.open(peticion, timeout=15) as respuesta:
            return respuesta.status, json.load(respuesta)
    except HTTPError as error:
        return error.code, json.load(error)


def preparar(raiz, cookies):
    dispositivos = json.loads(
        (raiz / "data" / "acceso-dispositivos.json").read_text(encoding="utf-8")
    )
    token = next(
        item["token"] for item in dispositivos
        if item["nombre"] == "navegador-portatil"
    )
    jar = MozillaCookieJar(cookies)
    opener = build_opener(HTTPCookieProcessor(jar))
    estado, creada = enviar(
        opener,
        "/auth/pairings",
        {"nombre": "Prueba fase 28b"},
        token,
    )
    if estado != 200:
        raise SystemExit(f"No se creó la vinculación: HTTP {estado}")
    estado, reclamada = enviar(
        opener,
        "/auth/pair/claim",
        {"codigo": creada["code"]},
    )
    if estado != 200 or reclamada.get("device") != "Prueba fase 28b":
        raise SystemExit(f"No se reclamó la vinculación: HTTP {estado}")
    estado_repetido, _ = enviar(
        opener,
        "/auth/pair/claim",
        {"codigo": creada["code"]},
    )
    if estado_repetido != 400:
        raise SystemExit("El código pudo usarse más de una vez")
    jar.save(ignore_discard=True, ignore_expires=True)
    print("Creación: 200 | reclamación: 200 | segundo uso: 400")


def verificar(cookies):
    jar = MozillaCookieJar(cookies)
    jar.load(ignore_discard=True, ignore_expires=True)
    opener = build_opener(HTTPCookieProcessor(jar))
    estado, datos = enviar(opener, "/status")
    esperado = {"name": "Prueba fase 28b", "administrator": False}
    if estado != 200 or datos.get("device") != esperado:
        raise SystemExit("La vinculación no sobrevivió al reinicio")
    print("Persistencia tras reinicio: OK | privilegio normal: OK")


def main():
    argumentos = ArgumentParser()
    argumentos.add_argument("accion", choices=["preparar", "verificar"])
    opciones = argumentos.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    cookies = raiz / "data" / "prueba-vinculacion.cookies"
    if opciones.accion == "preparar":
        preparar(raiz, cookies)
    else:
        verificar(cookies)


if __name__ == "__main__":
    main()
