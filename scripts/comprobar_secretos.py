"""Impide subir a Git los secretos privados conocidos por ASTRO."""

import json
from pathlib import Path
import subprocess

from dotenv import dotenv_values


def main():
    raiz = Path(__file__).resolve().parents[1]
    secretos = set()
    for nombre in (".env", ".env.acceso", ".env.vapid"):
        for clave, valor in dotenv_values(raiz / nombre).items():
            es_secreto = (
                clave.endswith("API_KEY")
                or "TOKEN" in clave
                or clave == "ASTRO_DISPOSITIVOS"
            )
            if es_secreto and valor and len(valor) >= 16 and not valor.startswith("pon_aqui"):
                secretos.add(valor.encode())
    dispositivos = raiz / "data" / "acceso-dispositivos.json"
    if dispositivos.is_file():
        for item in json.loads(dispositivos.read_text(encoding="utf-8")):
            secretos.add(item["token"].encode())
    salida = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=raiz,
        check=True,
        capture_output=True,
    ).stdout
    hallazgos = []
    for nombre in salida.decode().split("\0"):
        if not nombre:
            continue
        contenido = (raiz / nombre).read_bytes()
        if any(secreto in contenido for secreto in secretos):
            hallazgos.append(nombre)
    if hallazgos:
        print("Archivos con secretos conocidos:")
        for nombre in hallazgos:
            print(nombre)
        raise SystemExit(1)
    print(f"Sin secretos conocidos en {len(salida.decode().split(chr(0))) - 1} archivos de Git.")


if __name__ == "__main__":
    main()
