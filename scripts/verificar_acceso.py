"""Comprueba el acceso desplegado sin imprimir credenciales ni usar IA."""

import asyncio
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import websockets


BASE = "https://astro-vps.tailbee6db.ts.net"
WS = "wss://astro-vps.tailbee6db.ts.net/ws"


def codigo(ruta, token=None, origen=None):
    cabeceras = {}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    if origen:
        cabeceras["Origin"] = origen
    try:
        with urlopen(Request(BASE + ruta, headers=cabeceras), timeout=10) as respuesta:
            return respuesta.status
    except HTTPError as error:
        return error.code


async def sesion_persistente(token):
    cabeceras = {"Authorization": f"Bearer {token}"}
    async with websockets.connect(WS, additional_headers=cabeceras) as conexion:
        primera = json.loads(await conexion.recv())
    async with websockets.connect(WS, additional_headers=cabeceras) as conexion:
        segunda = json.loads(await conexion.recv())
    return primera["session"] == segunda["session"]


def main():
    ruta = Path(__file__).resolve().parents[1] / "data" / "acceso-dispositivos.json"
    dispositivos = {
        item["nombre"]: item["token"]
        for item in json.loads(ruta.read_text(encoding="utf-8"))
    }
    voz = dispositivos["voz-portatil"]
    navegador = dispositivos["navegador-portatil"]
    resultados = {
        "anonimo_status": codigo("/status"),
        "origen_ajeno": codigo("/status", navegador, "https://maliciosa.test"),
        "voz_status": codigo("/status", voz),
        "voz_sin_administracion": codigo("/ai/settings", voz),
        "navegador_administrador": codigo("/ai/settings", navegador),
        "sesion_persistente": asyncio.run(sesion_persistente(voz)),
    }
    esperados = {
        "anonimo_status": 401,
        "origen_ajeno": 403,
        "voz_status": 200,
        "voz_sin_administracion": 403,
        "navegador_administrador": 200,
        "sesion_persistente": True,
    }
    for nombre, resultado in resultados.items():
        print(f"{nombre}: {resultado}")
    if resultados != esperados:
        raise SystemExit("La comprobación de acceso no coincide con lo esperado")


if __name__ == "__main__":
    main()
