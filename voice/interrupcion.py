"""Detección de interrupción para uso con auriculares, sin cancelación de eco."""

from collections import deque

from clients.grabar_audio import cargar_sounddevice
from voice.detectar_voz import nivel_rms_pcm16


def escuchar_interrupcion(dispositivo, terminar, al_detectar):
    audio = cargar_sounddevice()
    info = audio.query_devices(dispositivo, "input")
    frecuencia = round(info["default_samplerate"])
    ventana = deque(maxlen=5)
    with audio.RawInputStream(samplerate=frecuencia, device=dispositivo,
                             channels=1, dtype="int16") as flujo:
        while not terminar.is_set():
            datos, _ = flujo.read(round(frecuencia * 0.03))
            ventana.append(nivel_rms_pcm16(bytes(datos)) >= 600)
            if sum(ventana) >= 3:
                al_detectar()
                return
