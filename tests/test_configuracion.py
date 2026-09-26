from copy import deepcopy

import pytest
import yaml

from core.chat import RUTA_CONFIG, cargar_configuracion


def test_cargar_configuracion_real() -> None:
    configuracion = cargar_configuracion()

    assert configuracion.proveedor.identificador == "openai"
    assert configuracion.proveedor.nombre_visible == "OpenAI"
    assert configuracion.modelo == "gpt-6-astra"
    assert configuracion.zona_horaria == "Europe/Madrid"
    assert configuracion.pasos_herramienta_maximos == 5


def test_configuracion_rechaza_limite_agente_invalido(tmp_path) -> None:
    datos = yaml.safe_load(RUTA_CONFIG.read_text(encoding="utf-8"))
    datos = deepcopy(datos)
    datos["agente"]["pasos_herramienta_maximos"] = 0
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        yaml.safe_dump(datos, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="pasos_herramienta_maximos",
    ):
        cargar_configuracion(ruta)


def test_cambiar_a_openrouter_solo_requiere_yaml(tmp_path) -> None:
    datos = yaml.safe_load(RUTA_CONFIG.read_text(encoding="utf-8"))
    datos = deepcopy(datos)
    datos["proveedor"] = "openrouter"
    datos["modelo"] = "openai/gpt-6-astra"
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        yaml.safe_dump(datos, allow_unicode=True),
        encoding="utf-8",
    )

    configuracion = cargar_configuracion(ruta)

    assert configuracion.proveedor.identificador == "openrouter"
    assert configuracion.proveedor.nombre_visible == "OpenRouter"
    assert configuracion.proveedor.base_url == "https://openrouter.ai/api/v1"
    assert configuracion.modelo == "openai/gpt-6-astra"


def test_configuracion_rechaza_proveedor_inexistente(tmp_path) -> None:
    datos = yaml.safe_load(RUTA_CONFIG.read_text(encoding="utf-8"))
    datos = deepcopy(datos)
    datos["proveedor"] = "desconocido"
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        yaml.safe_dump(datos, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no está configurado"):
        cargar_configuracion(ruta)
