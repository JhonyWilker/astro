"""Registro privado de frases de voz descartadas por destinatario."""

from datetime import datetime
import json
from pathlib import Path


RUTA_REGISTRO = (
    Path(__file__).resolve().parents[1]
    / "logs"
    / "falsos_positivos_voz.jsonl"
)


def registrar_falso_positivo(
    origen: str,
    motivo: str,
    caracteres: int,
    ruta: Path = RUTA_REGISTRO,
) -> None:
    if origen not in {"activation", "followup"}:
        raise ValueError("El origen no es válido")
    if not motivo or caracteres < 1:
        raise ValueError("El descarte no es válido")
    registro = {
        "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
        "origen": origen,
        "motivo": motivo,
        "caracteres": caracteres,
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as archivo:
        json.dump(registro, archivo, ensure_ascii=False)
        archivo.write("\n")
