"""Supervisor independiente del cliente de voz de ASTRO en Windows."""

import json
import logging
import os
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from gui.instancia import BloqueoInstancia


RAIZ = Path(__file__).resolve().parents[1]
CARPETA_ESTADO = RAIZ / "data" / "gui"
RUTA_BLOQUEO = CARPETA_ESTADO / "supervisor.lock"
RUTA_ESTADO = CARPETA_ESTADO / "supervisor.json"
RUTA_LOG = CARPETA_ESTADO / "supervisor.log"
RUTA_LOG_VOZ = CARPETA_ESTADO / "voz.log"


@dataclass
class PoliticaReinicio:
    maximo: int = 3
    ventana_segundos: float = 60.0
    estable_segundos: float = 300.0
    fallos: deque[float] = field(default_factory=deque)

    def siguiente_espera(
        self,
        ahora: float,
        duracion: float,
    ) -> float | None:
        if duracion >= self.estable_segundos:
            self.fallos.clear()
        while self.fallos and ahora - self.fallos[0] > self.ventana_segundos:
            self.fallos.popleft()
        if len(self.fallos) >= self.maximo:
            return None
        self.fallos.append(ahora)
        return float(min(2 ** (len(self.fallos) - 1), 8))


def ejecutable_sin_consola(ejecutable: str | None = None) -> str:
    ruta = Path(ejecutable or sys.executable)
    if os.name == "nt" and ruta.name.casefold() == "python.exe":
        candidato = ruta.with_name("pythonw.exe")
        if candidato.exists():
            return str(candidato)
    return str(ruta)


def _dispositivo(nombre: str, predeterminado: str = "") -> int | None:
    valor = os.getenv(nombre, predeterminado).strip()
    if not valor:
        return None
    numero = int(valor)
    if numero < 0:
        raise ValueError(f"{nombre} no puede ser negativo")
    return numero


def comando_voz(ejecutable: str | None = None) -> list[str]:
    comando = [
        ejecutable_sin_consola(ejecutable),
        "-m",
        "clients.voz",
        "--activacion",
        "--puente",
    ]
    microfono = _dispositivo("ASTRO_MICROFONO", "1")
    altavoz = _dispositivo("ASTRO_ALTAVOZ")
    if microfono is not None:
        comando.extend(("--microfono", str(microfono)))
    if altavoz is not None:
        comando.extend(("--altavoz", str(altavoz)))
    return comando


def _guardar_estado(estado: str, voz_pid: int | None, reinicios: int) -> None:
    CARPETA_ESTADO.mkdir(parents=True, exist_ok=True)
    temporal = RUTA_ESTADO.with_suffix(".tmp")
    temporal.write_text(
        json.dumps({
            "version": 1,
            "estado": estado,
            "supervisor_pid": os.getpid(),
            "voz_pid": voz_pid,
            "reinicios": reinicios,
            "actualizado": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporal.replace(RUTA_ESTADO)


def _opciones_windows() -> int:
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP


def supervisar(
    crear_proceso: Callable = subprocess.Popen,
    dormir: Callable[[float], None] = time.sleep,
    reloj: Callable[[], float] = time.monotonic,
    politica: PoliticaReinicio | None = None,
) -> int:
    bloqueo = BloqueoInstancia(RUTA_BLOQUEO)
    if not bloqueo.adquirir():
        return 0
    politica = politica or PoliticaReinicio()
    CARPETA_ESTADO.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=RUTA_LOG,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    reinicios = 0
    try:
        with RUTA_LOG_VOZ.open("a", encoding="utf-8", buffering=1) as salida:
            while True:
                inicio = reloj()
                proceso = crear_proceso(
                    comando_voz(),
                    cwd=RAIZ,
                    stdin=subprocess.DEVNULL,
                    stdout=salida,
                    stderr=subprocess.STDOUT,
                    env={
                        **os.environ,
                        "PYTHONUNBUFFERED": "1",
                        "PYTHONIOENCODING": "utf-8",
                    },
                    creationflags=_opciones_windows(),
                )
                _guardar_estado("activo", proceso.pid, reinicios)
                codigo = proceso.wait()
                duracion = max(0.0, reloj() - inicio)
                if codigo == 0:
                    _guardar_estado("detenido", None, reinicios)
                    return 0
                espera = politica.siguiente_espera(reloj(), duracion)
                if espera is None:
                    logging.error("Límite de reinicios del cliente de voz alcanzado")
                    _guardar_estado("limite_reinicios", None, reinicios)
                    return 1
                reinicios += 1
                logging.warning(
                    "Cliente de voz terminó con código %s; reinicio %s en %.0f s",
                    codigo,
                    reinicios,
                    espera,
                )
                _guardar_estado("esperando_reinicio", None, reinicios)
                dormir(espera)
    except Exception:
        logging.exception("El supervisor no pudo mantener el cliente de voz")
        _guardar_estado("error", None, reinicios)
        return 1
    finally:
        bloqueo.liberar()


def lanzar_independiente(
    crear_proceso: Callable = subprocess.Popen,
) -> object:
    return crear_proceso(
        [ejecutable_sin_consola(), "-m", "gui.supervisor"],
        cwd=RAIZ,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=_opciones_windows(),
    )


def main() -> int:
    return supervisar()


if __name__ == "__main__":
    raise SystemExit(main())
