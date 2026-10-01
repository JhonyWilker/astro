"""Valida que voz y PWA usan la conversación canónica del núcleo."""

import asyncio
import json
import os
from pathlib import Path
from secrets import token_hex
from time import perf_counter

from dotenv import load_dotenv
import websockets


RAIZ = Path(__file__).resolve().parents[1]
WS_PREDETERMINADO = "wss://astro-vps.tailbee6db.ts.net/ws"
RUTA_DISPOSITIVOS = RAIZ / "data" / "acceso-dispositivos.json"


def cargar_token(nombre: str) -> str:
    dispositivos = json.loads(RUTA_DISPOSITIVOS.read_text(encoding="utf-8"))
    for dispositivo in dispositivos:
        if dispositivo.get("nombre") == nombre:
            return str(dispositivo["token"])
    raise RuntimeError(f"No existe el dispositivo de prueba {nombre!r}")


async def conectar(nombre: str):
    url = os.getenv("ASTRO_WS_URL", WS_PREDETERMINADO)
    conexion = await websockets.connect(
        url,
        additional_headers={
            "Authorization": f"Bearer {cargar_token(nombre)}",
        },
    )
    listo = json.loads(await conexion.recv())
    if listo.get("type") != "ready":
        await conexion.close()
        raise RuntimeError(f"El núcleo no aceptó {nombre!r}")
    return conexion, listo


async def preguntar(conexion, texto: str) -> dict:
    await conexion.send(json.dumps({"type": "message", "text": texto}))
    inicio = perf_counter()
    primer_texto = None
    respuesta = ""
    herramientas = []
    while True:
        evento = json.loads(await conexion.recv())
        tipo = evento.get("type")
        if tipo == "delta":
            primer_texto = primer_texto or perf_counter() - inicio
            respuesta += str(evento.get("text", ""))
        elif tipo == "state" and evento.get("state") == "executing":
            herramientas.append(str(evento.get("tool")))
        elif tipo == "done":
            await conexion.send(json.dumps({
                "type": "played",
                "characters": len(respuesta),
            }))
            return {
                "text": respuesta,
                "first_text_seconds": primer_texto,
                "tools": herramientas,
                "provider": evento.get("provider"),
                "model": evento.get("model"),
            }
        elif tipo in {"error", "busy", "cancelled"}:
            raise RuntimeError(f"Turno fallido: {evento}")


async def validar() -> None:
    marcador = f"orion-{token_hex(3)}"
    voz, inicio_voz = await conectar("voz-portatil")
    try:
        await preguntar(
            voz,
            f"Conserva durante esta conversación el código {marcador}.",
        )
        calculo = await preguntar(voz, "Calcula 12 por 4")
        sesion_voz = inicio_voz.get("session")
    finally:
        await voz.close()

    pwa, inicio_pwa = await conectar("navegador-portatil")
    try:
        historial = inicio_pwa.get("history", [])
        contenido = " ".join(
            str(mensaje.get("content", "")) for mensaje in historial
        )
        sesion_pwa = inicio_pwa.get("session")
    finally:
        await pwa.close()

    if not sesion_voz or sesion_voz != sesion_pwa:
        raise RuntimeError("Voz y PWA no comparten identificador de sesión")
    if marcador not in contenido:
        raise RuntimeError("La PWA no recibió el contexto creado por voz")
    if "calcular" not in calculo["tools"]:
        raise RuntimeError("La ruta de voz no ejecutó la herramienta calcular")

    print("Sesión compartida: sí")
    print("Contexto de voz visible desde PWA: sí")
    print("Herramienta calcular desde voz: sí")
    print(
        "Ruta de IA: "
        f"{calculo['provider']}/{calculo['model']} · "
        f"primer texto {calculo['first_text_seconds']:.3f} s"
    )


if __name__ == "__main__":
    load_dotenv(RAIZ / ".env")
    asyncio.run(validar())
