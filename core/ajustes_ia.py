from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import monotonic
import json
import os


RUTA_AJUSTES = Path(
    os.getenv(
        "ASTRO_AI_SETTINGS_PATH",
        Path(__file__).resolve().parents[1] / "data" / "ajustes_ia.json",
    )
)


@dataclass(frozen=True)
class AjustesIA:
    principal: str
    respaldo: str
    modelos: dict[str, str]
    cambio_automatico: bool
    reintento_principal_segundos: int


class ServicioAjustesIA:
    def __init__(
        self,
        proveedores: set[str],
        ajustes_predeterminados: AjustesIA,
        ruta: Path = RUTA_AJUSTES,
        reloj: Callable[[], float] = monotonic,
    ) -> None:
        self._proveedores = frozenset(proveedores)
        self._predeterminados = ajustes_predeterminados
        self._ruta = ruta
        self._reloj = reloj
        self._bloqueo = RLock()
        self._ajustes = self._cargar()
        self._proveedor_activo = self._ajustes.principal
        self._principal_no_disponible_hasta = 0.0
        self._ultimo_error: str | None = None

    def _validar(self, ajustes: AjustesIA) -> None:
        if ajustes.principal not in self._proveedores:
            raise ValueError("El proveedor principal no está configurado")
        if ajustes.respaldo not in self._proveedores:
            raise ValueError("El proveedor de respaldo no está configurado")
        if ajustes.principal == ajustes.respaldo:
            raise ValueError("El principal y el respaldo deben ser distintos")
        if set(ajustes.modelos) != set(self._proveedores):
            raise ValueError("Falta el modelo de algún proveedor")
        if any(not modelo.strip() for modelo in ajustes.modelos.values()):
            raise ValueError("Los modelos no pueden estar vacíos")
        if not 10 <= ajustes.reintento_principal_segundos <= 3600:
            raise ValueError("El reintento debe estar entre 10 y 3600 segundos")

    def _cargar(self) -> AjustesIA:
        if not self._ruta.exists():
            self._validar(self._predeterminados)
            return self._predeterminados
        try:
            datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            ajustes = AjustesIA(
                principal=datos["principal"],
                respaldo=datos["respaldo"],
                modelos=dict(datos["modelos"]),
                cambio_automatico=datos["cambio_automatico"],
                reintento_principal_segundos=(
                    datos["reintento_principal_segundos"]
                ),
            )
            self._validar(ajustes)
            return ajustes
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Los ajustes de IA no son válidos: {self._ruta}"
            ) from error

    def obtener(self) -> AjustesIA:
        with self._bloqueo:
            return AjustesIA(
                principal=self._ajustes.principal,
                respaldo=self._ajustes.respaldo,
                modelos=dict(self._ajustes.modelos),
                cambio_automatico=self._ajustes.cambio_automatico,
                reintento_principal_segundos=(
                    self._ajustes.reintento_principal_segundos
                ),
            )

    def actualizar(self, ajustes: AjustesIA) -> AjustesIA:
        self._validar(ajustes)
        datos = {
            "principal": ajustes.principal,
            "respaldo": ajustes.respaldo,
            "modelos": ajustes.modelos,
            "cambio_automatico": ajustes.cambio_automatico,
            "reintento_principal_segundos": (
                ajustes.reintento_principal_segundos
            ),
        }
        with self._bloqueo:
            self._ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal = self._ruta.with_suffix(".tmp")
            temporal.write_text(
                json.dumps(datos, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporal.chmod(0o600)
            temporal.replace(self._ruta)
            self._ajustes = ajustes
            self._proveedor_activo = ajustes.principal
            self._principal_no_disponible_hasta = 0.0
            self._ultimo_error = None
            return self.obtener()

    def rutas_para_turno(self) -> tuple[str, ...]:
        with self._bloqueo:
            if not self._ajustes.cambio_automatico:
                return (self._ajustes.principal,)
            if self._reloj() < self._principal_no_disponible_hasta:
                return (self._ajustes.respaldo,)
            return (self._ajustes.principal, self._ajustes.respaldo)

    def registrar_fallo(self, proveedor: str, mensaje: str) -> None:
        with self._bloqueo:
            if proveedor == self._ajustes.principal:
                self._principal_no_disponible_hasta = (
                    self._reloj()
                    + self._ajustes.reintento_principal_segundos
                )
            self._ultimo_error = mensaje

    def registrar_exito(self, proveedor: str) -> tuple[str, str] | None:
        with self._bloqueo:
            anterior = self._proveedor_activo
            self._proveedor_activo = proveedor
            if proveedor == self._ajustes.principal:
                self._principal_no_disponible_hasta = 0.0
                self._ultimo_error = None
            if anterior == proveedor:
                return None
            return anterior, proveedor

    def estado(self) -> dict[str, object]:
        with self._bloqueo:
            restante = max(
                0,
                int(self._principal_no_disponible_hasta - self._reloj()),
            )
            return {
                "active": self._proveedor_activo,
                "degraded": self._proveedor_activo != self._ajustes.principal,
                "retry_in_seconds": restante,
                "last_error": self._ultimo_error,
            }
