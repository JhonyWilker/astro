"""Genera credenciales locales sin imprimir secretos ni sobrescribir existentes."""

import json
from pathlib import Path
from secrets import token_urlsafe

from dotenv import set_key


def main():
    raiz = Path(__file__).resolve().parents[1]
    destino = raiz / ".env.acceso"
    entrega = raiz / "data" / "acceso-dispositivos.json"
    if destino.exists() or entrega.exists():
        raise SystemExit("Ya existen credenciales; no se sobrescriben.")
    dispositivos = [
        {"nombre": "voz-portatil", "usuario": "jhony", "token": token_urlsafe(32), "administrador": False},
        {"nombre": "navegador-portatil", "usuario": "jhony", "token": token_urlsafe(32), "administrador": True},
        {"nombre": "iphone", "usuario": "jhony", "token": token_urlsafe(32), "administrador": True},
    ]
    entrega.parent.mkdir(parents=True, exist_ok=True)
    # Creación exclusiva: una repetición nunca reemplaza claves existentes.
    with entrega.open("x", encoding="utf-8") as archivo:
        json.dump(dispositivos, archivo, ensure_ascii=False, indent=2)
    with destino.open("x", encoding="utf-8") as archivo:
        archivo.write("ASTRO_ORIGENES=https://astro-vps.tailbee6db.ts.net\n")
        archivo.write("ASTRO_DISPOSITIVOS='" + json.dumps(dispositivos) + "'\n")
    set_key(raiz / ".env", "ASTRO_DEVICE_TOKEN", dispositivos[0]["token"])
    print("Credenciales preparadas en archivos privados excluidos de Git.")


if __name__ == "__main__":
    main()
