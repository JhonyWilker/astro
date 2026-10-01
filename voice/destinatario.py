"""Registro privado de frases de voz descartadas por destinatario."""

from datetime import datetime
import json
from pathlib import Path
import re
import unicodedata


RUTA_REGISTRO = (
    Path(__file__).resolve().parents[1]
    / "logs"
    / "falsos_positivos_voz.jsonl"
)


INICIOS_DIRECTOS = (
    "abre ",
    "activa ",
    "ayudame ",
    "busca ",
    "calcula ",
    "cambia ",
    "cierra ",
    "continua ",
    "crea ",
    "dime ",
    "explica ",
    "guardalo ",
    "guarda ",
    "haz ",
    "necesito ",
    "para ",
    "pon ",
    "puedes ",
    "podrias ",
    "recuerda ",
    "repite ",
    "sigue ",
    "vuelve ",
    "quiero ",
)
RESPUESTAS_DIRECTAS = {
    "adelante",
    "claro",
    "continua",
    "correcto",
    "dale",
    "hecho",
    "listo",
    "no",
    "repitelo",
    "si",
    "sigue",
    "vale",
}
FRASES_AJENAS = (
    "hablaba con ",
    "le hablaba a ",
    "no es contigo",
    "no te hablaba",
    "se lo decia a ",
)


def _normalizar(texto: str) -> str:
    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto.casefold())
        if unicodedata.category(caracter) != "Mn"
    )
    return " ".join(sin_acentos.split())


def clasificar_destinatario_local(texto: str) -> tuple[bool, str] | None:
    """Resuelve solo casos inequívocos y delega cualquier duda al núcleo."""
    normalizado = _normalizar(texto)
    limpio = re.sub(r"^[¿¡!?,.;:\-]+|[¿¡!?,.;:\-]+$", "", normalizado)
    if any(frase in limpio for frase in FRASES_AJENAS):
        return False, "other_person"
    if re.match(r"^astro(?:\b|$)", limpio):
        return True, "direct_mention"
    if limpio in RESPUESTAS_DIRECTAS:
        return True, "continuation"
    if limpio.startswith(INICIOS_DIRECTOS):
        return True, "continuation"
    return None


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
