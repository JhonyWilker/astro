from copy import deepcopy

import pytest
import yaml

from core.chat import RUTA_CONFIG, cargar_configuracion


def test_cargar_configuracion_real() -> None:
    configuracion = cargar_configuracion()

    assert configuracion.proveedor.identificador == "openai"
    assert configuracion.proveedor.nombre_visible == "OpenAI"
    assert configuracion.modelo == "gpt-6-astra"
    assert configuracion.nivel_servicio == "fast"
    assert configuracion.niveles_servicio_por_proveedor == {
        "openai": "fast",
        "openrouter": "default",
    }
    assert configuracion.zona_horaria == "Europe/Madrid"
    assert configuracion.pasos_herramienta_maximos == 5
    assert configuracion.esfuerzo_razonamiento == "low"
    assert configuracion.conversacion_rapida is not None
    assert configuracion.conversacion_rapida.modelo == "gpt-6-luna"
    assert configuracion.conversacion_rapida.nivel_servicio == "fast"
    assert configuracion.conversacion_rapida.esfuerzo_razonamiento == "none"
    assert configuracion.conversacion_rapida.tarifas.entrada_usd_millon == 0.20
    assert configuracion.conversacion_rapida.tarifas.salida_usd_millon == 1.00


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


def test_configuracion_rechaza_razonamiento_invalido(tmp_path) -> None:
    datos = yaml.safe_load(RUTA_CONFIG.read_text(encoding="utf-8"))
    datos = deepcopy(datos)
    datos["razonamiento"] = "ninguno"
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        yaml.safe_dump(datos, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="razonamiento"):
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
    assert configuracion.proveedor_respaldo == "openai"


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


def test_configuracion_rechaza_nivel_de_servicio_invalido(tmp_path) -> None:
    datos = yaml.safe_load(RUTA_CONFIG.read_text(encoding="utf-8"))
    datos = deepcopy(datos)
    datos["proveedores"]["openai"]["nivel_servicio"] = "turbo-inventado"
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        yaml.safe_dump(datos, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="nivel de servicio"):
        cargar_configuracion(ruta)
