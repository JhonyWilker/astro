import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

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
) -> ResultadoStreaming:
    cola_audio: asyncio.Queue[Path | None] = asyncio.Queue()

    async def producir_audio() -> None:
        indice = 0
        try:
            while True:
                texto = await cola_texto.get()
                if texto is None:
                    return
                indice += 1
                ruta = ruta_base.with_name(
                    f"{ruta_base.stem}-{indice:03d}{ruta_base.suffix}"
                )
                await asyncio.to_thread(
                    sintetizador,
                    texto,
                    voz,
                    configuracion_voz,
                    ruta,
                )
                await cola_audio.put(ruta)
        finally:
            await cola_audio.put(None)

    async def consumir_audio() -> ResultadoStreaming:
        fragmentos = 0
        cortes = 0
        latencia: float | None = None

        while True:
            ruta = await cola_audio.get()
            if ruta is None:
                break
            if latencia is None:
                latencia = reloj() - inicio
            desbordado = await asyncio.to_thread(
                reproductor,
                ruta,
                dispositivo,
            )
            fragmentos += 1
            cortes += int(desbordado)

        if latencia is None:
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
