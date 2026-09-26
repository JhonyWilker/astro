import pytest

import core.proveedores as proveedores
from core.proveedores import ConfiguracionProveedor


def proveedor_prueba() -> ConfiguracionProveedor:
    return ConfiguracionProveedor(
        identificador="prueba",
        nombre_visible="Proveedor de prueba",
        base_url="https://ia.example/v1",
        clave_entorno="CLAVE_PROVEEDOR_PRUEBA",
    )


def test_crear_cliente_usa_url_clave_y_limites(monkeypatch) -> None:
    opciones_recibidas = {}

    class ClienteFalso:
        def __init__(self, **opciones) -> None:
            opciones_recibidas.update(opciones)

    monkeypatch.setenv("CLAVE_PROVEEDOR_PRUEBA", "secreto-de-prueba")
    monkeypatch.setattr(proveedores, "OpenAI", ClienteFalso)

    proveedores.crear_cliente_responses(proveedor_prueba(), 12.5, 3)

    assert opciones_recibidas == {
        "api_key": "secreto-de-prueba",
        "base_url": "https://ia.example/v1",
        "timeout": 12.5,
        "max_retries": 3,
    }


def test_crear_cliente_rechaza_clave_ausente(monkeypatch) -> None:
    monkeypatch.delenv("CLAVE_PROVEEDOR_PRUEBA", raising=False)

    with pytest.raises(RuntimeError, match="CLAVE_PROVEEDOR_PRUEBA"):
        proveedores.crear_cliente_responses(proveedor_prueba(), 30, 2)
