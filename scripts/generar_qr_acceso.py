"""Genera localmente un QR de vinculación sin mostrar el token."""

from argparse import ArgumentParser
import json
from pathlib import Path

import segno


def main():
    argumentos = ArgumentParser()
    argumentos.add_argument("dispositivo")
    opciones = argumentos.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    datos = json.loads(
        (raiz / "data" / "acceso-dispositivos.json").read_text(encoding="utf-8")
    )
    tokens = {item["nombre"]: item["token"] for item in datos}
    if opciones.dispositivo not in tokens:
        raise SystemExit("Dispositivo desconocido")
    carpeta = raiz / "data" / "vinculacion"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"vincular-{opciones.dispositivo}.png"
    segno.make(tokens[opciones.dispositivo], error="h").save(
        destino,
        scale=10,
        border=4,
        dark="#06131f",
        light="#ffffff",
    )
    print(f"QR privado creado: {destino}")


if __name__ == "__main__":
    main()
