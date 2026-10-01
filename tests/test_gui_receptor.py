import time

from PySide6.QtCore import QCoreApplication

from gui.receptor import ReceptorPuente
from voice.estados import EstadoVoz
from voice.puente import PuenteLocal


def esperar_qt(condicion, segundos=3.0) -> bool:
    aplicacion = QCoreApplication.instance() or QCoreApplication([])
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        aplicacion.processEvents()
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_receptor_gui_se_autentica_y_recibe_estado_real(tmp_path) -> None:
    ruta = tmp_path / "puente.json"
    puente = PuenteLocal(ruta_info=ruta)
    assert puente.iniciar()
    receptor = ReceptorPuente(ruta_info=ruta, espera_reintento=0.02)
    conexiones = []
    eventos = []
    receptor.conexion.connect(conexiones.append)
    receptor.evento.connect(eventos.append)
    try:
        receptor.iniciar()
        assert esperar_qt(lambda: True in conexiones)
        assert esperar_qt(lambda: any(e.get("type") == "hello" for e in eventos))

        puente.publicar_estado(EstadoVoz.ESCUCHANDO, "Habla ahora")

        assert esperar_qt(
            lambda: any(
                e.get("type") == "state" and e.get("state") == "escuchando"
                for e in eventos
            )
        )
    finally:
        receptor.detener()
        puente.detener()

