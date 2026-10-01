"""Reproducción y escucha alineadas para cancelar el eco de ASTRO."""

from queue import Empty
from threading import Event
from typing import Any, Callable

import numpy as np

from voice.eco import FRECUENCIA_ECO_HZ, MUESTRAS_ECO


BLOQUES_PREBUFFER_DUPLEX = 20
BLOQUES_REBUFFER_DUPLEX = 10


def _actualizar_retardo_desde_portaudio(detector: Any, tiempo: Any) -> None:
    """Alinea AEC con los tiempos reales del ADC y del DAC."""
    if tiempo is None or not hasattr(detector, "actualizar_retardo"):
        return
    try:
        retardo_ms = (
            float(tiempo.outputBufferDacTime)
            - float(tiempo.inputBufferAdcTime)
        ) * 1000.0
    except (AttributeError, TypeError, ValueError):
        return
    detector.actualizar_retardo(retardo_ms)


def reproducir_pcm_streaming(
    cola_audio: Any,
    frecuencia_hz: int,
    microfono: int | None,
    altavoz: int | None,
    control: Any,
    al_primer_audio: Callable[[], Any] | None = None,
    al_confirmar: Callable[[int], Any] | None = None,
    detector: Any | None = None,
    al_detectar: Callable[[], Any] | None = None,
    *,
    modulo_audio: Any | None = None,
) -> tuple[int, int]:
    """Reproduce PCM incremental en un único flujo, con AEC si se solicita."""
    if frecuencia_hz <= 0:
        raise ValueError("La frecuencia de streaming debe ser positiva")
    if detector is not None and frecuencia_hz != FRECUENCIA_ECO_HZ:
        raise ValueError("La cancelación de eco requiere PCM a 16 kHz")
    if detector is not None and al_detectar is None:
        raise ValueError("La escucha dúplex necesita aviso de interrupción")
    if modulo_audio is None:
        from voice.hablar import cargar_sounddevice

        modulo_audio = cargar_sounddevice()

    muestras_bloque = (
        MUESTRAS_ECO
        if detector is not None
        else max(1, int(frecuencia_hz * 0.01))
    )
    bytes_bloque = muestras_bloque * 2
    pendiente = bytearray()
    marcas: list[tuple[int, int | None]] = []
    bytes_recibidos = 0
    bytes_reproducidos = 0
    terminado = False
    primer_audio = False
    fragmentos = 0
    cortes = 0

    def recibir_hasta(minimo: int) -> None:
        nonlocal bytes_recibidos, terminado
        while len(pendiente) < minimo and not terminado:
            elemento = cola_audio.get()
            if elemento is None:
                terminado = True
                break
            datos = bytes(getattr(elemento, "datos", b""))
            if datos:
                if len(datos) % 2:
                    raise ValueError("El PCM incremental debe contener muestras completas")
                pendiente.extend(datos)
                bytes_recibidos += len(datos)
            if getattr(elemento, "fin_fragmento", False):
                marcas.append((bytes_recibidos, getattr(elemento, "confirmado", None)))

    def confirmar_marcas() -> None:
        nonlocal fragmentos
        while marcas and marcas[0][0] <= bytes_reproducidos:
            _, confirmado = marcas.pop(0)
            fragmentos += 1
            if confirmado is not None and al_confirmar is not None:
                al_confirmar(confirmado)

    # El audio de red llega a ráfagas. El dúplex necesita margen suficiente
    # para que PortAudio no inserte huecos entre palabras.
    bloques_prebuffer = BLOQUES_PREBUFFER_DUPLEX if detector is not None else 10
    recibir_hasta(bytes_bloque * bloques_prebuffer)
    if not pendiente:
        return 0, 0

    def siguiente_bloque() -> tuple[np.ndarray, int]:
        recibir_hasta(bytes_bloque)
        cantidad = min(bytes_bloque, len(pendiente))
        datos = bytes(pendiente[:cantidad])
        del pendiente[:cantidad]
        referencia = np.zeros(muestras_bloque, dtype=np.int16)
        if datos:
            muestras = np.frombuffer(datos, dtype=np.int16)
            referencia[:len(muestras)] = muestras
        return referencia, cantidad

    if detector is not None:
        detector.preparar_fragmento()
        dispositivos = None
        if microfono is not None or altavoz is not None:
            predeterminados = modulo_audio.default.device
            dispositivos = (
                microfono if microfono is not None else predeterminados[0],
                altavoz if altavoz is not None else predeterminados[1],
            )
        finalizado = Event()
        errores: list[BaseException] = []

        rebufferizando = False

        def incorporar_disponible(minimo: int) -> None:
            nonlocal bytes_recibidos, terminado
            while len(pendiente) < minimo and not terminado:
                try:
                    elemento = cola_audio.get_nowait()
                except Empty:
                    return
                if elemento is None:
                    terminado = True
                    return
                datos = bytes(getattr(elemento, "datos", b""))
                if datos:
                    if len(datos) % 2:
                        raise ValueError(
                            "El PCM incremental debe contener muestras completas"
                        )
                    pendiente.extend(datos)
                    bytes_recibidos += len(datos)
                if getattr(elemento, "fin_fragmento", False):
                    marcas.append((
                        bytes_recibidos,
                        getattr(elemento, "confirmado", None),
                    ))

        def callback(indata, outdata, frames, tiempo, estado) -> None:
            nonlocal bytes_reproducidos, primer_audio, cortes, rebufferizando
            try:
                if frames != muestras_bloque:
                    raise RuntimeError("PortAudio no entregó bloques de 10 ms")
                cortes += int(bool(estado))
                if control.is_set():
                    outdata.fill(0)
                    raise modulo_audio.CallbackAbort
                minimo = (
                    bytes_bloque * BLOQUES_REBUFFER_DUPLEX
                    if rebufferizando
                    else bytes_bloque
                )
                incorporar_disponible(minimo)
                if len(pendiente) < minimo and not terminado:
                    rebufferizando = True
                    cortes += 1
                    outdata.fill(0)
                    return
                rebufferizando = False
                if not pendiente:
                    outdata.fill(0)
                    if terminado:
                        confirmar_marcas()
                        raise modulo_audio.CallbackStop
                    cortes += 1
                    return

                cantidad = min(bytes_bloque, len(pendiente))
                datos = bytes(pendiente[:cantidad])
                del pendiente[:cantidad]
                referencia = np.zeros(muestras_bloque, dtype=np.int16)
                muestras = np.frombuffer(datos, dtype=np.int16)
                referencia[:len(muestras)] = muestras
                outdata[:, 0] = referencia

                _actualizar_retardo_desde_portaudio(detector, tiempo)
                if detector.procesar(indata[:, 0].copy(), referencia):
                    if control.detectar():
                        al_detectar()
                    outdata.fill(0)
                    raise modulo_audio.CallbackAbort
                if not primer_audio:
                    primer_audio = True
                    if al_primer_audio is not None:
                        al_primer_audio()
                bytes_reproducidos += cantidad
                confirmar_marcas()
            except (modulo_audio.CallbackAbort, modulo_audio.CallbackStop):
                raise
            except BaseException as error:
                errores.append(error)
                outdata.fill(0)
                raise modulo_audio.CallbackAbort

        with modulo_audio.Stream(
            samplerate=frecuencia_hz,
            blocksize=muestras_bloque,
            device=dispositivos,
            channels=(1, 1),
            dtype="int16",
            callback=callback,
            finished_callback=finalizado.set,
        ) as flujo:
            if not finalizado.wait(90.0):
                flujo.abort()
                raise RuntimeError("El flujo PCM dúplex no terminó a tiempo")
        if errores:
            raise errores[0]
    else:
        with modulo_audio.RawOutputStream(
            samplerate=frecuencia_hz,
            device=altavoz,
            channels=1,
            dtype="int16",
        ) as flujo:
            while pendiente or not terminado:
                if control.is_set():
                    flujo.abort()
                    break
                referencia, cantidad = siguiente_bloque()
                if not cantidad:
                    confirmar_marcas()
                    break
                if not primer_audio:
                    primer_audio = True
                    if al_primer_audio is not None:
                        al_primer_audio()
                cortes += int(bool(flujo.write(referencia.tobytes())))
                bytes_reproducidos += cantidad
                confirmar_marcas()

    if control.is_set():
        control.registrar_detencion()
    return fragmentos, cortes


def reproducir_duplex(
    muestras: np.ndarray,
    microfono: int | None,
    altavoz: int | None,
    detector: Any,
    control: Any,
    al_detectar: Callable[[], Any],
    al_primer_audio: Callable[[], Any] | None = None,
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
    primer_audio_enviado = False

    def callback(indata, outdata, frames, tiempo, estado) -> None:
        nonlocal posicion, estado_incorrecto, primer_audio_enviado
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
            if not primer_audio_enviado and cantidad > 0:
                primer_audio_enviado = True
                if al_primer_audio is not None:
                    al_primer_audio()

            _actualizar_retardo_desde_portaudio(detector, tiempo)
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
