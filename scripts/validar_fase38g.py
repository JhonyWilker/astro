"""Valida el silencio duro local sin mostrar credenciales del puente."""
import argparse
import asyncio
import json
import time

import websockets.asyncio.client as ws_client

from gui.monitor import leer_info
from voice.silencio import RUTA_ESTADO


async def recibir(conexion, timeout=3.0):
    return json.loads(await asyncio.wait_for(conexion.recv(), timeout))


async def esperar_estado(conexion, esperado):
    while True:
        evento = await recibir(conexion)
        if evento.get("type") == "state" and evento.get("state") == esperado:
            return evento


async def comprobar_sin_niveles(conexion):
    limite_gracia = time.monotonic() + 0.2
    while time.monotonic() < limite_gracia:
        try:
            await recibir(conexion, 0.05)
        except asyncio.TimeoutError:
            pass
    limite = time.monotonic() + 0.5
    while time.monotonic() < limite:
        try:
            evento = await recibir(conexion, 0.1)
        except asyncio.TimeoutError:
            continue
        if evento.get("type") == "mic_level":
            raise AssertionError("El micrófono siguió publicando nivel silenciado")


def estado_persistente():
    datos = json.loads(RUTA_ESTADO.read_text(encoding="utf-8"))
    return datos.get("muted") is True


async def validar(modo):
    info = leer_info()
    if info is None:
        raise RuntimeError("El puente local de voz no está disponible")
    puerto, token = info
    async with ws_client.connect(f"ws://127.0.0.1:{puerto}") as conexion:
        await conexion.send(json.dumps({"type": "auth", "token": token}))
        hola = await recibir(conexion)
        if hola.get("type") != "hello":
            raise AssertionError("El puente no confirmó la autenticación")

        if modo == "silenciar":
            await conexion.send(json.dumps({
                "type": "set_mic_muted",
                "muted": True,
            }))
            await esperar_estado(conexion, "microfono_apagado")
            if not estado_persistente():
                raise AssertionError("El silencio no quedó guardado")
            await comprobar_sin_niveles(conexion)
            print("OK: micrófono cerrado y silencio guardado")
        elif modo == "comprobar-silencio":
            if hola.get("state") != "microfono_apagado":
                raise AssertionError("La voz no recuperó el silencio al reiniciar")
            if not estado_persistente():
                raise AssertionError("El archivo no conserva el silencio")
            await comprobar_sin_niveles(conexion)
            print("OK: el reinicio conserva el micrófono cerrado")
        else:
            await conexion.send(json.dumps({
                "type": "set_mic_muted",
                "muted": False,
            }))
            await esperar_estado(conexion, "dormido")
            while (await recibir(conexion)).get("type") != "mic_level":
                pass
            if estado_persistente():
                raise AssertionError("La reactivación no quedó guardada")
            print("OK: micrófono reactivado y nivel recibido")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "modo",
        choices=("silenciar", "comprobar-silencio", "reactivar"),
    )
    asyncio.run(validar(parser.parse_args().modo))


if __name__ == "__main__":
    main()
