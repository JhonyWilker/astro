from datetime import datetime
from zoneinfo import ZoneInfo

NOMBRE_HERRAMIENTA = "obtener_fecha_hora"

DEFINICION_HERRAMIENTA = {
    "type": "function",
    "name": NOMBRE_HERRAMIENTA,
    "description": (
        "Devuelve la fecha y hora actuales en la zona horaria configurada "
        "de Jhony. Úsala siempre que la respuesta dependa de la fecha, "
        "el día de la semana o la hora actuales."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
    "strict": True,
}

DIAS_SEMANA = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def obtener_fecha_hora(
    zona_horaria: str,
    ahora: datetime | None = None,
) -> dict[str, str]:
    zona = ZoneInfo(zona_horaria)
    if ahora is not None and ahora.tzinfo is None:
        raise ValueError("'ahora' debe incluir zona horaria")

    instante = ahora.astimezone(zona) if ahora else datetime.now(zona)
    desfase = instante.strftime("%z")
    desfase_con_dos_puntos = f"{desfase[:3]}:{desfase[3:]}"

    return {
        "fecha_iso": instante.date().isoformat(),
        "hora": instante.strftime("%H:%M:%S"),
        "dia_semana": DIAS_SEMANA[instante.weekday()],
        "fecha_legible": (
            f"{DIAS_SEMANA[instante.weekday()]}, "
            f"{instante.day} de {MESES[instante.month - 1]} "
            f"de {instante.year}"
        ),
        "zona_horaria": zona_horaria,
        "desfase_utc": desfase_con_dos_puntos,
    }
