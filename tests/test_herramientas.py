from datetime import datetime, timezone

import pytest

from tools.base import ContextoHerramienta, Riesgo
from tools.calculadora import ErrorCalculo, calcular
from tools.fecha_hora import obtener_fecha_hora
from tools.registro import RegistroHerramientas


def test_fecha_hora_convierte_a_madrid() -> None:
    resultado = obtener_fecha_hora(
        "Europe/Madrid",
        datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc),
    )

    assert resultado["fecha_iso"] == "2026-01-15"
    assert resultado["hora"] == "13:30:00"
    assert resultado["dia_semana"] == "jueves"
    assert resultado["desfase_utc"] == "+01:00"


def test_calculadora_conserva_exactitud_decimal() -> None:
    resultado = calcular("(0.1 + 0.2) * 10")

    assert resultado["resultado_exacto"] == "3"
    assert resultado["resultado_decimal"] == "3"


def test_calculadora_rechaza_codigo() -> None:
    with pytest.raises(ErrorCalculo):
        calcular("__import__('os').getcwd()")


def test_registro_descubre_metadatos() -> None:
    registro = RegistroHerramientas.descubrir()
    herramientas = registro.listar()

    assert [item.nombre for item in herramientas] == [
        "calcular",
        "obtener_fecha_hora",
    ]
    assert all(item.descripcion for item in herramientas)
    assert all(item.parametros for item in herramientas)
    assert all(item.riesgo is Riesgo.BAJO for item in herramientas)


def test_registro_ejecuta_y_controla_error() -> None:
    registro = RegistroHerramientas.descubrir()
    contexto = ContextoHerramienta(zona_horaria="Europe/Madrid")

    correcto = registro.ejecutar(
        "calcular",
        {"expresion": "7 * (8 + 2)"},
        contexto,
    )
    error = registro.ejecutar(
        "calcular",
        {"expresion": "1 / 0"},
        contexto,
    )

    assert correcto["resultado_exacto"] == "70"
    assert error == {"error": "No se puede dividir entre cero"}
