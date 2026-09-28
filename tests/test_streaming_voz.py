import asyncio
from pathlib import Path

import pytest

from voice.streaming import (
    SegmentadorTexto,
    reproducir_cola_streaming,
)


def test_segmentador_emite_frases_completas() -> None:
    segmentador = SegmentadorTexto()

    primera = segmentador.agregar("Hola, Jhony. Esta es ")
    segunda = segmentador.agregar("la segunda frase.")
    final = segmentador.finalizar()

    assert primera == ("Hola, Jhony.",)
    assert segunda == ("Esta es la segunda frase.",)
    assert final == ()


def test_segmentador_libera_primer_fragmento_sin_puntuacion() -> None:
    segmentador = SegmentadorTexto()

    partes = segmentador.agregar(
        "Jhony, estoy preparando una respuesta bastante larga "
        "que todavía no tiene ningún punto"
    )

    assert partes
    assert len(partes[0]) <= 45
    assert segmentador.finalizar()


def test_streaming_sintetiza_y_reproduce_en_orden(
    tmp_path: Path,
) -> None:
    sintetizados = []
    reproducidos = []

    def sintetizador(texto, voz, configuracion, ruta):
        sintetizados.append((texto, ruta.name))

    def reproductor(ruta, dispositivo):
        reproducidos.append((ruta.name, dispositivo))
        return False

    async def ejecutar_prueba():
        cola = asyncio.Queue()
        await cola.put("Primero.")
        await cola.put("Segundo.")
        await cola.put(None)
        return await reproducir_cola_streaming(
            cola,
            object(),
            object(),
            3,
            tmp_path / "respuesta.wav",
            inicio=10.0,
            sintetizador=sintetizador,
            reproductor=reproductor,
            reloj=lambda: 12.0,
        )

    resultado = asyncio.run(ejecutar_prueba())

    assert sintetizados == [
        ("Primero.", "respuesta-001.wav"),
        ("Segundo.", "respuesta-002.wav"),
    ]
    assert reproducidos == [
        ("respuesta-001.wav", 3),
        ("respuesta-002.wav", 3),
    ]
    assert resultado.fragmentos == 2
    assert resultado.latencia_primera_voz == pytest.approx(2.0)
    assert resultado.cortes_reproduccion == 0
