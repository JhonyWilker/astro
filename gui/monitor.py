"""Receptor mínimo del puente local de voz: imprime los eventos en tiempo real.

Uso: python -m gui.monitor
"""
import asyncio
import json
import sys
from pathlib import Path

import websockets.asyncio.client as ws_client
from websockets.exceptions import WebSocketException

RUTA_INFO = Path(__file__).resolve().parents[1] / "data" / "puente.json"
ESPERA_REINTENTO = 2.0


def leer_info(ruta=RUTA_INFO):
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return int(datos["port"]), str(datos["token"])
    except (OSError, ValueError, KeyError):
        return None


def describir(evento):
    tipo = evento.get("type")
    if tipo == "hello":
        return f"conectado · estado actual: {evento.get('state')}"
    if tipo == "state":
        return f"estado -> {evento.get('state')} · {evento.get('detail')}"
    if tipo == "transcript":
        return f"Jhony dijo: {evento.get('text')}"
    return f"{tipo}: {evento}"


async def escuchar(ruta=RUTA_INFO):
    while True:
        info = leer_info(ruta)
        if info is None:
            print("Esperando al cliente de voz (no existe data/puente.json)…", flush=True)
            await asyncio.sleep(ESPERA_REINTENTO)
            continue
        puerto, token = info
        try:
            async with ws_client.connect(f"ws://127.0.0.1:{puerto}") as conexion:
                await conexion.send(json.dumps({"type": "auth", "token": token}))
                async for mensaje in conexion:
                    print(describir(json.loads(mensaje)), flush=True)
        except (OSError, WebSocketException):
            pass
        print("Puente no disponible; reintentando…", flush=True)
        await asyncio.sleep(ESPERA_REINTENTO)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(escuchar())
    except KeyboardInterrupt:
        pass
