"""Mide el primer texto del núcleo sin imprimir credenciales."""

import asyncio
from argparse import ArgumentParser
import json
from pathlib import Path
from time import perf_counter

import websockets


RAIZ = Path(__file__).resolve().parents[1]
WS = "wss://astro-vps.tailbee6db.ts.net/ws"


async def medir(texto: str) -> None:
    ruta = RAIZ / "data" / "acceso-dispositivos.json"
    dispositivos = {
        item["nombre"]: item["token"]
        for item in json.loads(ruta.read_text(encoding="utf-8"))
    }
    cabecera = {
        "Authorization": f"Bearer {dispositivos['voz-portatil']}"
    }
    async with websockets.connect(
        WS,
        additional_headers=cabecera,
    ) as conexion:
        await conexion.recv()
        inicio = perf_counter()
        await conexion.send(json.dumps({
            "type": "message",
            "text": texto,
        }))
        primer_texto = None
        herramientas = []
        while True:
            evento = json.loads(await conexion.recv())
            tipo = evento.get("type")
            if tipo == "delta" and primer_texto is None:
                primer_texto = perf_counter() - inicio
            elif tipo == "state" and evento.get("state") == "executing":
                herramientas.append(str(evento.get("tool")))
            elif tipo == "done":
                print(f"Primer texto: {primer_texto:.3f} s")
                print(f"Modelo: {evento.get('model')}")
                print(f"Proveedor: {evento.get('provider')}")
                print(f"Herramientas: {', '.join(herramientas) or 'ninguna'}")
                break
            elif tipo == "error":
                raise RuntimeError(str(evento.get("message")))


def crear_argumentos() -> ArgumentParser:
    argumentos = ArgumentParser()
    argumentos.add_argument("texto")
    return argumentos


if __name__ == "__main__":
    asyncio.run(medir(crear_argumentos().parse_args().texto))
