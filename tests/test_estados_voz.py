import numpy as np
import pytest

from voice.estados import (
    FRECUENCIA_SENAL_HZ,
    EstadoVoz,
    IndicadorEstados,
    SENALES,
    generar_senal,
    reproducir_senal,
)


class FlujoFalso:
    def __init__(self) -> None:
        self.datos = b""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def write(self, datos):
        self.datos += datos


class AudioFalso:
    def __init__(self) -> None:
        self.opciones = None
        self.flujo = FlujoFalso()

    def RawOutputStream(self, **opciones):
        self.opciones = opciones
        return self.flujo


def test_cada_estado_tiene_una_senal_pcm16() -> None:
    for estado in EstadoVoz:
        pcm = generar_senal(estado)

        assert pcm.dtype == np.int16
        assert len(pcm) > 0
        assert int(np.abs(pcm).max()) <= round(32767 * 0.11)
        assert len(SENALES[estado]) >= 1


def test_reproduce_la_senal_en_el_altavoz_elegido() -> None:
    audio = AudioFalso()

    reproducir_senal(EstadoVoz.ESCUCHANDO, 4, audio)

    assert audio.opciones == {
        "samplerate": FRECUENCIA_SENAL_HZ,
        "device": 4,
        "channels": 1,
        "dtype": "int16",
    }
    assert audio.flujo.datos


def test_indicador_publica_la_secuencia_completa() -> None:
    mensajes = []
    sonidos = []
    indicador = IndicadorEstados(
        dispositivo=3,
        salida=mensajes.append,
        reproductor=lambda estado, dispositivo: sonidos.append(
            (estado, dispositivo)
        ),
    )

    secuencia = (
        EstadoVoz.DORMIDO,
        EstadoVoz.ESCUCHANDO,
        EstadoVoz.PENSANDO,
        EstadoVoz.EJECUTANDO,
        EstadoVoz.PENSANDO,
        EstadoVoz.HABLANDO,
        EstadoVoz.DORMIDO,
    )
    for estado in secuencia:
        indicador.cambiar(estado)

    assert sonidos == [(estado, 3) for estado in secuencia]
    assert mensajes[0] == "[DORMIDO] Esperando «Astro»"
    assert mensajes[-1] == "[DORMIDO] Esperando «Astro»"


def test_no_repite_un_estado_ni_su_sonido() -> None:
    sonidos = []
    indicador = IndicadorEstados(
        salida=lambda _: None,
        reproductor=lambda estado, dispositivo: sonidos.append(estado),
    )

    assert indicador.cambiar(EstadoVoz.DORMIDO) is True
    assert indicador.cambiar(EstadoVoz.DORMIDO) is False
    assert sonidos == [EstadoVoz.DORMIDO]


def test_despues_de_hablar_puede_escuchar_un_seguimiento() -> None:
    indicador = IndicadorEstados(sonidos=False, salida=lambda _: None)
    for estado in (
        EstadoVoz.DORMIDO,
        EstadoVoz.ESCUCHANDO,
        EstadoVoz.PENSANDO,
        EstadoVoz.HABLANDO,
        EstadoVoz.ESCUCHANDO,
    ):
        indicador.cambiar(estado)

    assert indicador.estado is EstadoVoz.ESCUCHANDO


def test_si_no_entiende_un_seguimiento_puede_escuchar_de_nuevo() -> None:
    indicador = IndicadorEstados(sonidos=False, salida=lambda _: None)
    for estado in (
        EstadoVoz.DORMIDO,
        EstadoVoz.ESCUCHANDO,
        EstadoVoz.PENSANDO,
        EstadoVoz.HABLANDO,
        EstadoVoz.ESCUCHANDO,
        EstadoVoz.PENSANDO,
        EstadoVoz.ESCUCHANDO,
    ):
        indicador.cambiar(estado)

    assert indicador.estado is EstadoVoz.ESCUCHANDO


def test_rechaza_una_transicion_imposible() -> None:
    indicador = IndicadorEstados(sonidos=False, salida=lambda _: None)
    indicador.cambiar(EstadoVoz.DORMIDO)

    with pytest.raises(ValueError, match="dormido -> hablando"):
        indicador.cambiar(EstadoVoz.HABLANDO)


def test_un_error_de_audio_deja_el_indicador_visual_activo() -> None:
    mensajes = []

    def fallar(*_):
        raise OSError("sin altavoz")

    indicador = IndicadorEstados(salida=mensajes.append, reproductor=fallar)
    indicador.cambiar(EstadoVoz.DORMIDO)
    indicador.cambiar(EstadoVoz.ESCUCHANDO)

    assert sum("AVISO" in mensaje for mensaje in mensajes) == 1
    assert mensajes[-1] == "[ESCUCHANDO] Habla ahora"


def test_el_gancho_recibe_cada_cambio_con_su_texto() -> None:
    recibidos = []
    indicador = IndicadorEstados(
        sonidos=False,
        salida=lambda _: None,
        al_cambiar=lambda estado, texto: recibidos.append((estado, texto)),
    )

    indicador.cambiar(EstadoVoz.DORMIDO)
    indicador.cambiar(EstadoVoz.ESCUCHANDO, "Habla ahora")
    indicador.cambiar(EstadoVoz.ESCUCHANDO, "repetido")  # sin cambio: no se notifica

    assert recibidos == [
        (EstadoVoz.DORMIDO, "Esperando «Astro»"),
        (EstadoVoz.ESCUCHANDO, "Habla ahora"),
    ]


def test_un_gancho_que_falla_no_derriba_la_conversacion() -> None:
    llamadas = []

    def gancho_roto(estado, texto):
        llamadas.append(estado)
        raise RuntimeError("fallo del receptor")

    indicador = IndicadorEstados(
        sonidos=False,
        salida=lambda _: None,
        al_cambiar=gancho_roto,
    )

    assert indicador.cambiar(EstadoVoz.DORMIDO) is True
    assert indicador.cambiar(EstadoVoz.ESCUCHANDO) is True
    assert indicador.estado is EstadoVoz.ESCUCHANDO
    assert llamadas == [EstadoVoz.DORMIDO]  # se desactivó tras el primer fallo
    assert indicador.al_cambiar is None
