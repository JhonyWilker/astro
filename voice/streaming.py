import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from threading import Event
from time import perf_counter
from typing import Any

from voice.duplex import reproducir_pcm_streaming
from voice.hablar import reproducir_wav, sintetizar


CARACTERES_PRIMER_FRAGMENTO = 45
CARACTERES_FRAGMENTO_LARGO = 140
PATRON_FINAL = re.compile(r'[.!?;](?:["»”)]*)?(?:\s+|$)|\n+')


@dataclass(frozen=True)
class ResultadoStreaming:
    fragmentos: int
    latencia_primera_voz: float
    cortes_reproduccion: int


class SegmentadorTexto:
    def __init__(self) -> None:
        self._pendiente = ""
        self._ha_emitido = False

    def agregar(self, texto: str) -> tuple[str, ...]:
        self._pendiente += texto
        salida: list[str] = []

        while True:
            corte = self._buscar_corte()
            if corte is None:
                break
            fragmento = self._pendiente[:corte].strip()
            self._pendiente = self._pendiente[corte:].lstrip()
            if fragmento:
                salida.append(fragmento)
                self._ha_emitido = True

        return tuple(salida)

    def finalizar(self) -> tuple[str, ...]:
        fragmento = self._pendiente.strip()
        self._pendiente = ""
        if not fragmento:
            return ()
        self._ha_emitido = True
        return (fragmento,)

    def _buscar_corte(self) -> int | None:
        coincidencia = PATRON_FINAL.search(self._pendiente)
        if coincidencia is not None:
            return coincidencia.end()

        limite = (
            CARACTERES_FRAGMENTO_LARGO
            if self._ha_emitido
            else CARACTERES_PRIMER_FRAGMENTO
        )
        if len(self._pendiente) < limite:
            return None

        minimo = max(1, limite // 2)
        espacio = self._pendiente.rfind(" ", minimo, limite + 1)
        if espacio >= minimo:
            return espacio + 1

        siguiente = self._pendiente.find(" ", limite)
        if siguiente >= 0:
            return siguiente + 1
        if len(self._pendiente) >= CARACTERES_FRAGMENTO_LARGO:
            return CARACTERES_FRAGMENTO_LARGO
        return None


@dataclass(frozen=True)
class FragmentoVoz:
    texto: str
    expresion: str | None = None


async def reproducir_cola_streaming(
    cola_texto: asyncio.Queue[str | None],
    voz: Any,
    configuracion_voz: Any,
    dispositivo: int | None,
    ruta_base: Path,
    inicio: float,
    sintetizador: Callable[..., Any] = sintetizar,
    reproductor: Callable[..., bool] = reproducir_wav,
    reloj: Callable[[], float] = perf_counter,
    detener: Any | None = None,
    confirmar: Any | None = None,
    al_empezar: Callable[[], None] | None = None,
    microfono: int | None = None,
    detector_eco: Any | None = None,
    al_detectar: Callable[[], Any] | None = None,
    reproductor_pcm: Callable[..., tuple[int, int]] = reproducir_pcm_streaming,
    turno_continuo: bool = False,
) -> ResultadoStreaming:
    if getattr(sintetizador, "streaming_disponible", False):
        cola_audio_pcm: Queue[Any] = Queue()
        control = detener if detener is not None else Event()
        latencia: float | None = None
        bucle = asyncio.get_running_loop()

        def marcar_primer_audio() -> None:
            nonlocal latencia
            if latencia is None:
                latencia = reloj() - inicio
                if al_empezar is not None:
                    al_empezar()

        def confirmar_desde_hilo(cantidad: int) -> None:
            if confirmar is None:
                return
            futuro = asyncio.run_coroutine_threadsafe(confirmar(cantidad), bucle)
            futuro.result(timeout=5.0)

        opciones_productor = (
            {"turno_continuo": True} if turno_continuo else {}
        )
        productor = asyncio.create_task(sintetizador.producir_streaming(
            cola_texto,
            cola_audio_pcm,
            ruta_base,
            **opciones_productor,
        ))
        consumidor = asyncio.create_task(asyncio.to_thread(
            reproductor_pcm,
            cola_audio_pcm,
            sintetizador.configuracion.frecuencia_streaming_hz,
            microfono,
            dispositivo,
            control,
            marcar_primer_audio,
            confirmar_desde_hilo,
            detector_eco,
            al_detectar,
        ))
        resultados = await asyncio.gather(
            productor,
            consumidor,
            return_exceptions=True,
        )
        for resultado in resultados:
            if isinstance(resultado, BaseException):
                raise resultado
        fragmentos, cortes = resultados[1]
        if latencia is None:
            if control.is_set():
                return ResultadoStreaming(0, 0.0, cortes)
            raise RuntimeError("No se generó audio incremental para la respuesta")
        return ResultadoStreaming(fragmentos, latencia, cortes)

    cola_audio: asyncio.Queue[Path | None] = asyncio.Queue()

    async def producir_audio() -> None:
        indice = 0
        try:
            while True:
                texto = await cola_texto.get()
                if texto is None:
                    return
                confirmado = None
                expresion = None
                if isinstance(texto, tuple):
                    if len(texto) == 3:
                        texto, confirmado, expresion = texto
                    else:
                        texto, confirmado = texto
                if detener is not None and detener.is_set():
                    continue
                indice += 1
                ruta = ruta_base.with_name(
                    f"{ruta_base.stem}-{indice:03d}{ruta_base.suffix}"
                )
                await asyncio.to_thread(
                    sintetizador,
                    FragmentoVoz(texto, expresion),
                    voz,
                    configuracion_voz,
                    ruta,
                )
                await cola_audio.put((ruta, confirmado))
        finally:
            await cola_audio.put(None)

    async def consumir_audio() -> ResultadoStreaming:
        fragmentos = 0
        cortes = 0
        latencia: float | None = None

        while True:
            item = await cola_audio.get()
            if item is None:
                break
            ruta, confirmado = item
            if detener is not None and detener.is_set():
                continue
            def marcar_primer_audio() -> None:
                nonlocal latencia
                if latencia is None:
                    latencia = reloj() - inicio
                    if al_empezar is not None:
                        al_empezar()

            opciones = {"detener": detener} if detener is not None else {}
            opciones["al_primer_audio"] = marcar_primer_audio
            if detector_eco is not None:
                opciones.update({
                    "microfono": microfono,
                    "detector_eco": detector_eco,
                    "al_detectar": al_detectar,
                })
            desbordado = await asyncio.to_thread(reproductor, ruta, dispositivo, **opciones)
            if detener is not None and detener.is_set():
                continue
            if confirmar is not None and confirmado is not None:
                await confirmar(confirmado)
            fragmentos += 1
            cortes += int(desbordado)

        if latencia is None:
            if detener is not None and detener.is_set():
                return ResultadoStreaming(0, 0.0, 0)
            raise RuntimeError("No se generó audio para la respuesta")
        return ResultadoStreaming(
            fragmentos=fragmentos,
            latencia_primera_voz=latencia,
            cortes_reproduccion=cortes,
        )

    resultados = await asyncio.gather(
        producir_audio(),
        consumir_audio(),
        return_exceptions=True,
    )
    for resultado in resultados:
        if isinstance(resultado, BaseException):
            raise resultado
    return resultados[1]
