"""Prueba cancelación y continuidad entre dispositivos contra el VPS."""

import asyncio
import json
from pathlib import Path

import websockets


WS = "wss://astro-vps.tailbee6db.ts.net/ws"


async def main():
    ruta = Path(__file__).resolve().parents[1] / "data" / "acceso-dispositivos.json"
    dispositivos = {
        item["nombre"]: item["token"]
        for item in json.loads(ruta.read_text(encoding="utf-8"))
    }
    cabecera_voz = {"Authorization": f"Bearer {dispositivos['voz-portatil']}"}
    async with websockets.connect(WS, additional_headers=cabecera_voz) as conexion:
        listo = json.loads(await conexion.recv())
        await conexion.send(json.dumps({
            "type": "message",
            "text": "Enumera del uno al cien, cada número con una explicación distinta.",
        }))
        fragmento = None
        while fragmento is None:
            evento = json.loads(await conexion.recv())
            if evento.get("type") == "delta":
                fragmento = evento["text"]
        await conexion.send(json.dumps({"type": "ack", "characters": len(fragmento)}))
        await conexion.send(json.dumps({"type": "cancel"}))
        while True:
            cancelado = json.loads(await conexion.recv())
            if cancelado.get("type") == "cancelled":
                break
            if cancelado.get("type") not in {"delta", "provider_change"}:
                raise RuntimeError("El servidor no confirmó la cancelación")

    cabecera_web = {"Authorization": f"Bearer {dispositivos['navegador-portatil']}"}
    async with websockets.connect(WS, additional_headers=cabecera_web) as conexion:
        recuperado = json.loads(await conexion.recv())
    historial = recuperado.get("history", [])
    if recuperado.get("session") != listo.get("session"):
        raise RuntimeError("Los dispositivos no compartieron conversación")
    if len(historial) != 2 or historial[-1].get("content") != fragmento:
        raise RuntimeError("El historial no conservó exactamente el prefijo confirmado")
    print("Cancelación remota: OK")
    print(f"Prefijo conservado: {len(fragmento)} caracteres")
    print("Conversación compartida entre voz y navegador: OK")


if __name__ == "__main__":
    asyncio.run(main())
