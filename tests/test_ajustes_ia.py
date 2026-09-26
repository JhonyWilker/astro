from pathlib import Path

from core.ajustes_ia import AjustesIA, ServicioAjustesIA


def ajustes_predeterminados() -> AjustesIA:
    return AjustesIA(
        principal="openai",
        respaldo="openrouter",
        modelos={
            "openai": "gpt-6-astra",
            "openrouter": "openai/gpt-6-astra",
        },
        cambio_automatico=True,
        reintento_principal_segundos=120,
    )


def crear_servicio(ruta: Path, reloj=lambda: 100.0) -> ServicioAjustesIA:
    return ServicioAjustesIA(
        proveedores={"openai", "openrouter"},
        ajustes_predeterminados=ajustes_predeterminados(),
        ruta=ruta,
        reloj=reloj,
    )


def test_ajustes_predeterminados_no_crean_archivo(tmp_path) -> None:
    ruta = tmp_path / "ajustes.json"

    servicio = crear_servicio(ruta)

    assert servicio.obtener() == ajustes_predeterminados()
    assert not ruta.exists()


def test_ajustes_actualizados_persisten(tmp_path) -> None:
    ruta = tmp_path / "ajustes.json"
    servicio = crear_servicio(ruta)
    nuevos = AjustesIA(
        principal="openrouter",
        respaldo="openai",
        modelos={
            "openai": "gpt-6-astra",
            "openrouter": "openai/gpt-6-astra",
        },
        cambio_automatico=False,
        reintento_principal_segundos=300,
    )

    servicio.actualizar(nuevos)
    recargado = crear_servicio(ruta)

    assert recargado.obtener() == nuevos


def test_respaldo_y_retorno_automatico(tmp_path) -> None:
    ahora = [100.0]
    servicio = crear_servicio(
        tmp_path / "ajustes.json",
        reloj=lambda: ahora[0],
    )

    assert servicio.rutas_para_turno() == ("openai", "openrouter")
    servicio.registrar_fallo("openai", "timeout")
    cambio = servicio.registrar_exito("openrouter")

    assert cambio == ("openai", "openrouter")
    assert servicio.rutas_para_turno() == ("openrouter",)
    assert servicio.estado()["degraded"] is True

    ahora[0] = 221.0
    assert servicio.rutas_para_turno() == ("openai", "openrouter")
    regreso = servicio.registrar_exito("openai")

    assert regreso == ("openrouter", "openai")
    assert servicio.estado()["degraded"] is False
