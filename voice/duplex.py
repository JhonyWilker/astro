"""Reproducción y escucha alineadas para cancelar el eco de ASTRO."""

from threading import Event
from typing import Any, Callable

import numpy as np

from voice.eco import FRECUENCIA_ECO_HZ, MUESTRAS_ECO


def reproducir_duplex(
    muestras: np.ndarray,
    microfono: int | None,
    altavoz: int | None,
    detector: Any,
    control: Any,
    al_detectar: Callable[[], Any],
    *,
    modulo_audio: Any,
) -> bool:
    """Reproduce y escucha el mismo bloque de 10 ms en un único callback."""
    muestras = np.asarray(muestras, dtype=np.int16).reshape(-1)
    detector.preparar_fragmento()
    terminado = Event()
    error: list[BaseException] = []
    posicion = 0
    estado_incorrecto = False

    def callback(indata, outdata, frames, tiempo, estado) -> None:
        nonlocal posicion, estado_incorrecto
        del tiempo
        try:
            if frames != MUESTRAS_ECO:
                raise RuntimeError("PortAudio no entregó bloques de 10 ms")
            estado_incorrecto |= bool(estado)
            referencia = np.zeros(MUESTRAS_ECO, dtype=np.int16)
            cantidad = min(MUESTRAS_ECO, len(muestras) - posicion)
            if cantidad > 0:
                referencia[:cantidad] = muestras[posicion:posicion + cantidad]
                posicion += cantidad
            outdata[:, 0] = referencia

            if detector.procesar(indata[:, 0].copy(), referencia):
                if control.detectar():
                    al_detectar()
                outdata.fill(0)
                raise modulo_audio.CallbackAbort
            if posicion >= len(muestras):
                raise modulo_audio.CallbackStop
        except (modulo_audio.CallbackAbort, modulo_audio.CallbackStop):
            raise
        except BaseException as excepcion:
            error.append(excepcion)
            outdata.fill(0)
            raise modulo_audio.CallbackAbort

    dispositivos = None
    if microfono is not None or altavoz is not None:
        predeterminados = modulo_audio.default.device
        dispositivos = (
            microfono if microfono is not None else predeterminados[0],
            altavoz if altavoz is not None else predeterminados[1],
        )
    duracion = len(muestras) / FRECUENCIA_ECO_HZ
    with modulo_audio.Stream(
        samplerate=FRECUENCIA_ECO_HZ,
        blocksize=MUESTRAS_ECO,
        device=dispositivos,
        channels=(1, 1),
        dtype="int16",
        callback=callback,
        finished_callback=terminado.set,
    ) as flujo:
        if not terminado.wait(min(60.0, max(5.0, duracion + 3.0))):
            flujo.abort()
            raise RuntimeError("El flujo dúplex no terminó a tiempo")

    if control.is_set():
        control.registrar_detencion()
    if error:
        raise error[0]
    return estado_incorrecto
