import json

from core.notificaciones import ServicioNotificaciones

SUSCRIPCION = {
    "endpoint": "https://push.example/suscripcion",
    "expirationTime": None,
    "keys": {
        "p256dh": "p" * 32,
        "auth": "a" * 16,
    },
}


def test_suscripcion_se_guarda_sin_duplicados(tmp_path) -> None:
    servicio = ServicioNotificaciones(tmp_path / "push.json")
    servicio.guardar(SUSCRIPCION)
    servicio.guardar(SUSCRIPCION)

    assert servicio.contar() == 1
    guardado = json.loads(
        (tmp_path / "push.json").read_text(encoding="utf-8")
    )
    assert guardado[0]["endpoint"] == SUSCRIPCION["endpoint"]


def test_notificacion_usa_vapid_y_payload_visible(tmp_path) -> None:
    llamadas = []

    def enviar_falso(**argumentos):
        llamadas.append(argumentos)

    clave = tmp_path / "private.pem"
    clave.write_text("privada", encoding="utf-8")
    servicio = ServicioNotificaciones(
        tmp_path / "push.json",
        clave_publica="publica",
        ruta_clave_privada=clave,
        sujeto="https://astro-vps.tailbee6db.ts.net",
        enviar=enviar_falso,
    )
    servicio.guardar(SUSCRIPCION)

    assert servicio.enviar_prueba() == (1, 0)
    assert llamadas[0]["vapid_claims"]["sub"].startswith("https://")
    assert "Notificación de prueba" in llamadas[0]["data"]
