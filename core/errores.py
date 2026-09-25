from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import json

RUTA_ERRORES = Path(__file__).resolve().parents[1] / "logs" / "errores.jsonl"


class ErrorRespuestaASTRO(Exception):
    """Error controlado durante una respuesta en streaming."""


class ErrorLimiteHerramientas(ErrorRespuestaASTRO):
    """El agente alcanzó el máximo de herramientas de un turno."""


@dataclass(frozen=True)
class RegistroError:
    fecha_hora: str
    tipo: str
    estado_http: int | None
    codigo: str | None
    reintentable: bool


def crear_registro_error(
    error: Exception,
    reintentable: bool,
) -> RegistroError:
    estado_http = getattr(error, "status_code", None)
    codigo_original = getattr(error, "code", None)
    codigo = str(codigo_original) if codigo_original else None
    return RegistroError(
        fecha_hora=datetime.now().astimezone().isoformat(timespec="seconds"),
        tipo=type(error).__name__,
        estado_http=estado_http,
        codigo=codigo,
        reintentable=reintentable,
    )


def guardar_registro_error(
    registro: RegistroError,
    ruta: Path = RUTA_ERRORES,
) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as archivo:
        json.dump(asdict(registro), archivo, ensure_ascii=False)
        archivo.write("\n")
