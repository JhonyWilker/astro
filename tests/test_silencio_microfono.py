import json
from threading import Event, Thread

import pytest

from voice.silencio import ControlMicrofono


def test_silencio_persiste_y_se_recupera_tras_reiniciar(tmp_path) -> None:
    ruta = tmp_path / "microfono.json"
    primero = ControlMicrofono(ruta)

    assert primero.silenciado is False
    assert primero.cambiar(True) is True
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"muted": True}
    assert ControlMicrofono(ruta).silenciado is True


def test_silenciar_cancela_todas_las_capturas_activas(tmp_path) -> None:
    control = ControlMicrofono(tmp_path / "microfono.json")
    una = control.nueva_cancelacion()
    otra = control.nueva_cancelacion()

    control.cambiar(True)

    assert una.is_set()
    assert otra.is_set()
    assert control.nueva_cancelacion().is_set()


def test_reactivar_desbloquea_la_espera_sin_reutilizar_cancelaciones(tmp_path) -> None:
    control = ControlMicrofono(tmp_path / "microfono.json")
    control.cambiar(True)
    termino = Event()
    hilo = Thread(target=lambda: (control.esperar_activo(), termino.set()))
    hilo.start()
    assert not termino.wait(0.05)

    control.cambiar(False)

    assert termino.wait(1)
    hilo.join()
    assert not control.nueva_cancelacion().is_set()


def test_estado_danado_arranca_con_microfono_activo(tmp_path) -> None:
    ruta = tmp_path / "microfono.json"
    ruta.write_text("no es json", encoding="utf-8")

    assert ControlMicrofono(ruta).silenciado is False


def test_rechaza_un_estado_que_no_sea_booleano(tmp_path) -> None:
    control = ControlMicrofono(tmp_path / "microfono.json")

    with pytest.raises(TypeError):
        control.cambiar(1)

