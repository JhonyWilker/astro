from copy import deepcopy

import pytest
import yaml

from core.chat import RUTA_CONFIG, cargar_configuracion


def test_cargar_configuracion_real() -> None:
    configuracion = cargar_configuracion()

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
