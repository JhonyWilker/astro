import asyncio
from pathlib import Path

import pytest

from voice.streaming import (
    FragmentoVoz,
    SegmentadorTexto,
    reproducir_cola_streaming,
)
from voice.interrupcion import ControlInterrupcion
from voice.proveedor_voz import BloquePCM


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
    estados = []

    def sintetizador(texto, voz, configuracion, ruta):
        sintetizados.append((texto, ruta.name))

    def reproductor(ruta, dispositivo, al_primer_audio):
        reproducidos.append((ruta.name, dispositivo))
        al_primer_audio()
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
            al_empezar=lambda: estados.append("hablando"),
        )

    resultado = asyncio.run(ejecutar_prueba())

    assert sintetizados == [
        (FragmentoVoz("Primero."), "respuesta-001.wav"),
        (FragmentoVoz("Segundo."), "respuesta-002.wav"),
    ]
    assert reproducidos == [
        ("respuesta-001.wav", 3),
        ("respuesta-002.wav", 3),
    ]
    assert resultado.fragmentos == 2
    assert resultado.latencia_primera_voz == pytest.approx(2.0)
    assert resultado.cortes_reproduccion == 0
    assert estados == ["hablando"]


def test_streaming_interrumpido_no_confirma_fragmento(tmp_path: Path) -> None:
    control = ControlInterrupcion()
    confirmados = []

    def reproductor(ruta, dispositivo, detener, al_primer_audio):
        al_primer_audio()
        control.detectar()
        control.registrar_detencion()
        return False

    async def confirmar(cantidad):
        confirmados.append(cantidad)

    async def ejecutar_prueba():
        cola = asyncio.Queue()
        await cola.put(("Una respuesta larga.", 20))
        await cola.put(None)
        return await reproducir_cola_streaming(
            cola,
            object(),
            object(),
            None,
            tmp_path / "respuesta.wav",
            inicio=0.0,
            sintetizador=lambda *args: None,
            reproductor=reproductor,
            detener=control,
            confirmar=confirmar,
        )

    resultado = asyncio.run(ejecutar_prueba())

    assert resultado.fragmentos == 0
    assert confirmados == []
    assert control.latencia_segundos is not None


def test_streaming_conserva_la_expresion_del_fragmento(
    tmp_path: Path,
) -> None:
    recibidos = []

    def reproducir(*_, al_primer_audio):
        al_primer_audio()
        return False

    async def ejecutar_prueba():
        cola = asyncio.Queue()
        await cola.put(("Una noticia.", 12, "excited, amazed, warmly proud"))
        await cola.put(None)
        return await reproducir_cola_streaming(
            cola,
            object(),
            object(),
            None,
            tmp_path / "respuesta.wav",
            inicio=0.0,
            sintetizador=lambda fragmento, *_: recibidos.append(fragmento),
            reproductor=reproducir,
            reloj=lambda: 0.1,
        )

    asyncio.run(ejecutar_prueba())

    assert recibidos == [
        FragmentoVoz("Una noticia.", "excited, amazed, warmly proud")
    ]


def test_streaming_usa_pcm_incremental_si_esta_disponible(tmp_path: Path) -> None:
    confirmados = []

    class Configuracion:
        frecuencia_streaming_hz = 16000

    class SintetizadorStreaming:
        streaming_disponible = True
        configuracion = Configuracion()

        async def producir_streaming(self, textos, audios, _ruta):
            elemento = await textos.get()
            assert elemento == ("Respuesta.", 10, None)
            audios.put(BloquePCM(b"\x01\x00" * 160))
            audios.put(BloquePCM(b"", 10, True))
            assert await textos.get() is None
            audios.put(None)

    def reproducir_pcm(
        audios, _frecuencia, _microfono, _altavoz, _control,
        al_primer_audio, al_confirmar, *_args,
    ):
        assert audios.get().datos
        al_primer_audio()
        frontera = audios.get()
        al_confirmar(frontera.confirmado)
        assert audios.get() is None
        return 1, 0

    async def confirmar(cantidad):
        confirmados.append(cantidad)

    async def ejecutar():
        cola = asyncio.Queue()
        await cola.put(("Respuesta.", 10, None))
        await cola.put(None)
        return await reproducir_cola_streaming(
            cola,
            object(),
            object(),
            None,
            tmp_path / "respuesta.wav",
            inicio=10.0,
            sintetizador=SintetizadorStreaming(),
            reloj=lambda: 10.25,
            confirmar=confirmar,
            reproductor_pcm=reproducir_pcm,
        )

    resultado = asyncio.run(ejecutar())

    assert resultado.fragmentos == 1
    assert resultado.latencia_primera_voz == pytest.approx(0.25)
    assert confirmados == [10]
