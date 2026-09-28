import asyncio
import json
import os
from dotenv import load_dotenv

import websockets
from websockets.exceptions import ConnectionClosed

URL_PREDETERMINADA = "ws://astro-vps:8000/ws"


async def conversar() -> None:
    load_dotenv()
    url = os.getenv("ASTRO_WS_URL", URL_PREDETERMINADA)
    print(f"Conectando con ASTRO en {url}...")

    try:
        token = os.getenv("ASTRO_DEVICE_TOKEN", "")
        async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as websocket:
            listo = json.loads(await websocket.recv())
            if listo.get("type") != "ready":
                raise RuntimeError("ASTRO no confirmó la conexión")

            print("ASTRO conectado. Escribe 'salir' para terminar.")
            while True:
                pregunta = (
                    await asyncio.to_thread(input, "\nJhony: ")
                ).strip()
                if pregunta.lower() == "salir":
                    print("Hasta luego, Jhony.")
                    return
                if not pregunta:
                    print("Escribe una pregunta.")
                    continue

                await websocket.send(
                    json.dumps(
                        {"type": "message", "text": pregunta},
                        ensure_ascii=False,
                    )
                )
                print("\nASTRO: ", end="", flush=True)
                caracteres = 0

                while True:
                    evento = json.loads(await websocket.recv())
                    if evento["type"] == "delta":
                        print(evento["text"], end="", flush=True)
                        caracteres += len(evento["text"])
                        await websocket.send(json.dumps({"type": "ack", "characters": caracteres}))
                    elif evento["type"] == "done":
                        await websocket.send(json.dumps({"type": "played", "characters": caracteres}))
                        print()
                        uso = evento["usage"]
                        tokens = sum(item["tokens"] for item in uso)
                        coste = sum(
                            item["coste_estimado_usd"]
                            for item in uso
                        )
                        print(
                            f"[{len(uso)} petición/es | "
                            f"{tokens} tokens | "
                            f"{coste:.6f} USD estimados]"
                        )
                        break
                    elif evento["type"] == "error":
                        await websocket.send(json.dumps({"type": "played", "characters": caracteres}))
                        print(f"\nError: {evento['message']}")
                        break
    except (OSError, ConnectionClosed) as error:
        print(f"No se pudo mantener la conexión: {error}")


def main() -> None:
    asyncio.run(conversar())


if __name__ == "__main__":
    main()
