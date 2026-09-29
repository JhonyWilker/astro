import pytest

from voice.seguimiento import VentanaSeguimiento


def test_ofrece_cinco_seguimientos_despues_de_abrirse() -> None:
    ventana = VentanaSeguimiento()

    ventana.abrir()
    restantes = [ventana.consumir() for _ in range(5)]

    assert restantes == [4, 3, 2, 1, 0]
    assert ventana.activa is False


def test_una_nueva_activacion_reinicia_el_limite() -> None:
    ventana = VentanaSeguimiento(limite=5)
    ventana.abrir()
    ventana.consumir()
    ventana.consumir()

    ventana.abrir()

    assert ventana.restantes == 5


def test_cerrar_descarta_los_seguimientos_pendientes() -> None:
    ventana = VentanaSeguimiento(limite=3)
    ventana.abrir()

    ventana.cerrar()

    assert ventana.activa is False
    with pytest.raises(RuntimeError, match="cerrada"):
        ventana.consumir()


@pytest.mark.parametrize("limite", [0, 11, 2.5, True])
def test_rechaza_limites_invalidos(limite) -> None:
    with pytest.raises(ValueError, match="entre 1 y 10"):
        VentanaSeguimiento(limite=limite)
