import json
import os
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from pywebpush import WebPushException, webpush

EnviarPush = Callable[..., Any]
RAIZ_PROYECTO = Path(__file__).resolve().parents[1]


class ErrorNotificaciones(Exception):
    pass


def validar_suscripcion(datos: dict[str, Any]) -> dict[str, Any]:
    endpoint = datos.get("endpoint")
    claves = datos.get("keys")

    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("https://")
        or len(endpoint) > 2048
    ):
        raise ValueError("La suscripción necesita un endpoint HTTPS válido")

    if not isinstance(claves, dict):
        raise ValueError("La suscripción no contiene claves")

    p256dh = claves.get("p256dh")
    auth = claves.get("auth")
    if not isinstance(p256dh, str) or not 16 <= len(p256dh) <= 512:
        raise ValueError("La clave p256dh no es válida")
    if not isinstance(auth, str) or not 8 <= len(auth) <= 256:
        raise ValueError("La clave auth no es válida")

    return {
        "endpoint": endpoint,
        "expirationTime": datos.get("expirationTime"),
        "keys": {"p256dh": p256dh, "auth": auth},
    }


class ServicioNotificaciones:
    def __init__(
        self,
        ruta_datos: Path,
        clave_publica: str = "",
        ruta_clave_privada: Path | None = None,
        sujeto: str = "",
        enviar: EnviarPush = webpush,
    ) -> None:
        self.ruta_datos = ruta_datos
        self.clave_publica = clave_publica.strip()
        self.ruta_clave_privada = ruta_clave_privada
        self.sujeto = sujeto.strip()
        self._enviar = enviar
        self._bloqueo = Lock()

    @classmethod
    def desde_entorno(cls) -> "ServicioNotificaciones":
        load_dotenv(RAIZ_PROYECTO / ".env")
        load_dotenv(RAIZ_PROYECTO / ".env.vapid")
        ruta_privada = os.getenv("ASTRO_VAPID_PRIVATE_KEY_PATH", "").strip()
        return cls(
            ruta_datos=Path(
                os.getenv(
                    "ASTRO_PUSH_DATA_PATH",
                    "data/push_subscriptions.json",
                )
            ),
            clave_publica=os.getenv("ASTRO_VAPID_PUBLIC_KEY", ""),
            ruta_clave_privada=Path(ruta_privada) if ruta_privada else None,
            sujeto=os.getenv("ASTRO_VAPID_SUBJECT", ""),
        )

    @property
    def configurado(self) -> bool:
        return bool(
            self.clave_publica
            and self.ruta_clave_privada
            and self.ruta_clave_privada.is_file()
            and self.sujeto
        )

    def _leer(self) -> list[dict[str, Any]]:
        if not self.ruta_datos.exists():
            return []
        try:
            datos = json.loads(self.ruta_datos.read_text(encoding="utf-8"))
            if not isinstance(datos, list):
                raise ValueError
            return [validar_suscripcion(item) for item in datos]
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ErrorNotificaciones(
                "No se pudo leer el registro de suscripciones"
            ) from error

    def _escribir(self, suscripciones: list[dict[str, Any]]) -> None:
        try:
            self.ruta_datos.parent.mkdir(parents=True, exist_ok=True)
            temporal = self.ruta_datos.with_suffix(".tmp")
            temporal.write_text(
                json.dumps(suscripciones, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporal.replace(self.ruta_datos)
        except OSError as error:
            raise ErrorNotificaciones(
                "No se pudo guardar el registro de suscripciones"
            ) from error

    def contar(self) -> int:
        with self._bloqueo:
            return len(self._leer())

    def guardar(self, datos: dict[str, Any]) -> int:
        suscripcion = validar_suscripcion(datos)
        with self._bloqueo:
            actuales = self._leer()
            actuales = [
                item
                for item in actuales
                if item["endpoint"] != suscripcion["endpoint"]
            ]
            actuales.append(suscripcion)
            self._escribir(actuales)
            return len(actuales)

    def eliminar(self, endpoint: str) -> int:
        with self._bloqueo:
            actuales = self._leer()
            restantes = [
                item for item in actuales if item["endpoint"] != endpoint
            ]
            if len(restantes) != len(actuales):
                self._escribir(restantes)
            return len(restantes)

    def enviar_prueba(self) -> tuple[int, int]:
        if not self.configurado:
            raise ErrorNotificaciones(
                "Las notificaciones push no están configuradas"
            )

        with self._bloqueo:
            suscripciones = self._leer()

        payload = json.dumps(
            {
                "title": "ASTRO",
                "body": "Notificación de prueba recibida correctamente.",
                "url": "/",
                "tag": "astro-prueba",
            },
            ensure_ascii=False,
        )
        enviados = 0
        fallos = 0
        caducados: list[str] = []

        for suscripcion in suscripciones:
            try:
                self._enviar(
                    subscription_info=suscripcion,
                    data=payload,
                    vapid_private_key=str(self.ruta_clave_privada),
                    vapid_claims={"sub": self.sujeto},
                    ttl=60,
                    timeout=15,
                )
                enviados += 1
            except WebPushException as error:
                fallos += 1
                estado = getattr(error.response, "status_code", None)
                if estado in {404, 410}:
                    caducados.append(suscripcion["endpoint"])

        for endpoint in caducados:
            self.eliminar(endpoint)

        return enviados, fallos
