from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
import json

RUTA_REGISTROS = Path(__file__).resolve().parents[1] / "logs" / "uso.jsonl"


@dataclass(frozen=True)
class Tarifas:
    entrada_usd_millon: float
    entrada_cache_usd_millon: float
    escritura_cache_usd_millon: float
    salida_usd_millon: float


@dataclass(frozen=True)
class RegistroUso:
    fecha_hora: str
    proveedor: str
    modelo: str
    servicio: str
    tokens_entrada: int
    tokens_entrada_cache: int
    tokens_escritura_cache: int
    tokens_salida: int
    tokens_razonamiento: int
    tokens_totales: int
    duracion_segundos: float
    coste_estimado_usd: float


def calcular_coste_estimado(
    tokens_entrada: int,
    tokens_entrada_cache: int,
    tokens_escritura_cache: int,
    tokens_salida: int,
    tarifas: Tarifas,
) -> float:
    tokens_entrada_normales = max(
        tokens_entrada - tokens_entrada_cache - tokens_escritura_cache,
        0,
    )
    coste = (
        tokens_entrada_normales * tarifas.entrada_usd_millon
        + tokens_entrada_cache * tarifas.entrada_cache_usd_millon
        + tokens_escritura_cache * tarifas.escritura_cache_usd_millon
        + tokens_salida * tarifas.salida_usd_millon
    ) / 1_000_000
    return coste


def crear_registro(
    *,
    proveedor: str,
    modelo: str,
    servicio: str,
    tokens_entrada: int,
    tokens_entrada_cache: int,
    tokens_escritura_cache: int,
    tokens_salida: int,
    tokens_razonamiento: int,
    tokens_totales: int,
    duracion_segundos: float,
    tarifas: Tarifas,
) -> RegistroUso:
    coste = calcular_coste_estimado(
        tokens_entrada,
        tokens_entrada_cache,
        tokens_escritura_cache,
        tokens_salida,
        tarifas,
    )
    return RegistroUso(
        fecha_hora=datetime.now().astimezone().isoformat(timespec="seconds"),
        proveedor=proveedor,
        modelo=modelo,
        servicio=servicio,
        tokens_entrada=tokens_entrada,
        tokens_entrada_cache=tokens_entrada_cache,
        tokens_escritura_cache=tokens_escritura_cache,
        tokens_salida=tokens_salida,
        tokens_razonamiento=tokens_razonamiento,
        tokens_totales=tokens_totales,
        duracion_segundos=round(duracion_segundos, 3),
        coste_estimado_usd=round(coste, 10),
    )


def guardar_registro(
    registro: RegistroUso,
    ruta: Path = RUTA_REGISTROS,
) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as archivo:
        json.dump(asdict(registro), archivo, ensure_ascii=False)
        archivo.write("\n")


def cargar_registros(ruta: Path = RUTA_REGISTROS) -> list[dict]:
    if not ruta.exists():
        return []

    registros = []
    with ruta.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if linea.strip():
                registros.append(json.loads(linea))
    return registros


def crear_informe_diario(
    fecha: date | None = None,
    ruta: Path = RUTA_REGISTROS,
) -> str:
    fecha_objetivo = fecha or datetime.now().astimezone().date()
    fecha_texto = fecha_objetivo.isoformat()
    registros = [
        registro
        for registro in cargar_registros(ruta)
        if str(registro.get("fecha_hora", "")).startswith(fecha_texto)
    ]

    peticiones = len(registros)
    tokens_entrada = sum(registro["tokens_entrada"] for registro in registros)
    tokens_salida = sum(registro["tokens_salida"] for registro in registros)
    tokens_totales = sum(registro["tokens_totales"] for registro in registros)
    tiempo_total = sum(registro["duracion_segundos"] for registro in registros)
    coste_total = sum(registro["coste_estimado_usd"] for registro in registros)

    return (
        f"Informe diario {fecha_texto}:\n"
        f"- Peticiones: {peticiones}\n"
        f"- Tokens de entrada: {tokens_entrada}\n"
        f"- Tokens de salida: {tokens_salida}\n"
        f"- Tokens totales: {tokens_totales}\n"
        f"- Tiempo total: {tiempo_total:.2f} s\n"
        f"- Coste estimado: {coste_total:.6f} USD"
    )


def resumir_registro(registro: RegistroUso) -> str:
    return (
        f"{registro.proveedor} · Uso: {registro.tokens_totales} tokens "
        f"({registro.tokens_entrada} entrada + "
        f"{registro.tokens_salida} salida) | "
        f"{registro.duracion_segundos:.2f} s | "
        f"{registro.coste_estimado_usd:.6f} USD estimados"
    )


def main() -> None:
    print(crear_informe_diario())


if __name__ == "__main__":
    main()
