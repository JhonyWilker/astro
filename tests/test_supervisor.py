from itertools import count
from pathlib import Path
from types import SimpleNamespace

from gui.instancia import BloqueoInstancia
import gui.supervisor as supervisor


def test_bloqueo_impide_duplicados_y_se_libera(tmp_path: Path) -> None:
    ruta = tmp_path / "instancia.lock"
    primero = BloqueoInstancia(ruta)
    segundo = BloqueoInstancia(ruta)

    assert primero.adquirir() is True
    assert segundo.adquirir() is False
    primero.liberar()
    assert segundo.adquirir() is True
    segundo.liberar()


def test_comando_voz_activa_wake_word_y_puente(monkeypatch) -> None:
    monkeypatch.setenv("ASTRO_MICROFONO", "3")
    monkeypatch.setenv("ASTRO_ALTAVOZ", "5")

    comando = supervisor.comando_voz("pythonw.exe")

    assert comando == [
        "pythonw.exe",
        "-m",
        "clients.voz",
        "--activacion",
        "--puente",
        "--microfono",
        "3",
        "--altavoz",
        "5",
    ]


def test_politica_limita_reinicios_y_olvida_tras_estabilidad() -> None:
    politica = supervisor.PoliticaReinicio()

    assert politica.siguiente_espera(0, 1) == 1
    assert politica.siguiente_espera(1, 1) == 2
    assert politica.siguiente_espera(2, 1) == 4
    assert politica.siguiente_espera(3, 1) is None
    assert politica.siguiente_espera(400, 300) == 1


def test_supervisor_reinicia_fallos_y_respeta_salida_normal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    codigos = iter((1, 1, 0))
    procesos = []
    esperas = []
    reloj = count()

    class Proceso:
        def __init__(self, codigo):
            self.pid = 100 + len(procesos)
            self.codigo = codigo

        def wait(self):
            return self.codigo

    def crear(*argumentos, **opciones):
        proceso = Proceso(next(codigos))
        procesos.append((proceso, argumentos, opciones))
        return proceso

    monkeypatch.setattr(supervisor, "CARPETA_ESTADO", tmp_path)
    monkeypatch.setattr(supervisor, "RUTA_BLOQUEO", tmp_path / "supervisor.lock")
    monkeypatch.setattr(supervisor, "RUTA_ESTADO", tmp_path / "supervisor.json")
    monkeypatch.setattr(supervisor, "RUTA_LOG", tmp_path / "supervisor.log")
    monkeypatch.setattr(supervisor, "RUTA_LOG_VOZ", tmp_path / "voz.log")
    monkeypatch.setattr(supervisor, "comando_voz", lambda: ["voz"])

    resultado = supervisor.supervisar(
        crear_proceso=crear,
        dormir=esperas.append,
        reloj=lambda: next(reloj),
    )

    assert resultado == 0
    assert len(procesos) == 3
    assert esperas == [1.0, 2.0]
    assert procesos[0][2]["env"]["PYTHONIOENCODING"] == "utf-8"
    assert '"estado": "detenido"' in (
        tmp_path / "supervisor.json"
    ).read_text(encoding="utf-8")


def test_supervisor_se_detiene_al_superar_limite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    contador = 0

    def crear(*_argumentos, **_opciones):
        nonlocal contador
        contador += 1
        return SimpleNamespace(pid=contador, wait=lambda: 1)

    tiempos = count()
    monkeypatch.setattr(supervisor, "CARPETA_ESTADO", tmp_path)
    monkeypatch.setattr(supervisor, "RUTA_BLOQUEO", tmp_path / "supervisor.lock")
    monkeypatch.setattr(supervisor, "RUTA_ESTADO", tmp_path / "supervisor.json")
    monkeypatch.setattr(supervisor, "RUTA_LOG", tmp_path / "supervisor.log")
    monkeypatch.setattr(supervisor, "RUTA_LOG_VOZ", tmp_path / "voz.log")
    monkeypatch.setattr(supervisor, "comando_voz", lambda: ["voz"])

    resultado = supervisor.supervisar(
        crear_proceso=crear,
        dormir=lambda _segundos: None,
        reloj=lambda: next(tiempos),
    )

    assert resultado == 1
    assert contador == 4
    assert '"estado": "limite_reinicios"' in (
        tmp_path / "supervisor.json"
    ).read_text(encoding="utf-8")
