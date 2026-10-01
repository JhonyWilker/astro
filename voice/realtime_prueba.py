"""Ruta experimental y reversible de audio a texto con OpenAI Realtime."""

import base64
from dataclasses import dataclass
import os
from pathlib import Path
import wave
from typing import Any, Callable

import numpy as np
from openai import AsyncOpenAI
from scipy.signal import resample_poly


MODELO_REALTIME = "gpt-realtime-2.1"


class ErrorRealtimePrueba(RuntimeError):
    """Fallo recuperable: el cliente debe volver a la ruta local."""


@dataclass(frozen=True)
class RespuestaRealtime:
    texto: str
    ordenar_silencio: bool = False


def leer_pcm_24khz(ruta: Path) -> bytes:
    with wave.open(str(ruta), "rb") as archivo:
        if archivo.getnchannels() != 1 or archivo.getsampwidth() != 2:
            raise ValueError("Realtime necesita un WAV PCM16 mono")
        frecuencia = archivo.getframerate()
        muestras = np.frombuffer(
            archivo.readframes(archivo.getnframes()),
            dtype=np.int16,
        )
    if frecuencia != 24000:
        from math import gcd

        divisor = gcd(frecuencia, 24000)
        muestras = resample_poly(
            muestras.astype(np.float32),
            24000 // divisor,
            frecuencia // divisor,
        )
        muestras = np.clip(np.rint(muestras), -32768, 32767).astype(np.int16)
    return muestras.tobytes()


class SesionRealtimePrueba:
    def __init__(
        self,
        instrucciones: str,
        *,
        cliente: Any | None = None,
        modelo: str = MODELO_REALTIME,
    ) -> None:
        clave = os.getenv("OPENAI_API_KEY", "").strip()
        if cliente is None and not clave:
            raise ErrorRealtimePrueba("Falta OPENAI_API_KEY")
        self._cliente = cliente or AsyncOpenAI(api_key=clave)
        self._instrucciones = instrucciones
        self._modelo = modelo
        self._gestor: Any | None = None
        self._conexion: Any | None = None
        self._respuesta_activa = False

    async def __aenter__(self) -> "SesionRealtimePrueba":
        try:
            self._gestor = self._cliente.realtime.connect(model=self._modelo)
            self._conexion = await self._gestor.__aenter__()
            await self._conexion.send({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": self._modelo,
                    "output_modalities": ["text"],
                    "instructions": self._instrucciones,
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "turn_detection": None,
                        }
                    },
                    "tools": [{
                        "type": "function",
                        "name": "dormir_astro",
                        "description": (
                            "Úsala únicamente cuando el usuario ordena de "
                            "forma explícita que ASTRO deje de hablar o se "
                            "calle, por ejemplo: cállate, silencio, shhh, "
                            "para de hablar o guarda silencio. No la uses "
                            "para correcciones, preguntas ni cambios de tema."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    }],
                    "tool_choice": "auto",
                },
            })
            await self._esperar("session.updated")
            await self._precalentar()
            return self
        except Exception as error:
            await self.__aexit__(type(error), error, error.__traceback__)
            raise ErrorRealtimePrueba("No se pudo abrir Realtime") from error

    async def __aexit__(self, tipo, error, traza) -> None:
        del tipo, error, traza
        self._respuesta_activa = False
        if self._gestor is not None:
            await self._gestor.__aexit__(None, None, None)
        self._gestor = None
        self._conexion = None

    async def responder(
        self,
        ruta_audio: Path,
        emitir: Callable[[str], None],
    ) -> RespuestaRealtime:
        if self._conexion is None:
            raise ErrorRealtimePrueba("La sesión Realtime no está abierta")
        pcm = leer_pcm_24khz(ruta_audio)
        partes: list[str] = []
        llamada_silencio: str | None = None
        try:
            await self._conexion.send({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm).decode("ascii"),
            })
            await self._conexion.send({"type": "input_audio_buffer.commit"})
            await self._conexion.send({
                "type": "response.create",
                "response": {"output_modalities": ["text"]},
            })
            self._respuesta_activa = True
            while True:
                evento = await self._conexion.recv()
                if evento.type == "error":
                    raise ErrorRealtimePrueba(str(evento.error))
                if evento.type == "response.output_text.delta":
                    fragmento = str(evento.delta)
                    partes.append(fragmento)
                    emitir(fragmento)
                elif evento.type == "response.done":
                    salida = getattr(
                        getattr(evento, "response", None),
                        "output",
                        (),
                    )
                    for elemento in salida:
                        if (
                            getattr(elemento, "type", "") == "function_call"
                            and getattr(elemento, "name", "")
                            == "dormir_astro"
                        ):
                            llamada_silencio = str(
                                getattr(elemento, "call_id", "")
                            )
                            break
                    break
        except ErrorRealtimePrueba:
            raise
        except Exception as error:
            raise ErrorRealtimePrueba("Falló la respuesta Realtime") from error
        finally:
            self._respuesta_activa = False
        texto = "".join(partes).strip()
        if llamada_silencio:
            await self._conexion.send({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": llamada_silencio,
                    "output": '{"dormido":true}',
                },
            })
            return RespuestaRealtime("", ordenar_silencio=True)
        if not texto:
            raise ErrorRealtimePrueba("Realtime terminó sin texto")
        return RespuestaRealtime(texto)

    async def cancelar(self) -> None:
        if self._conexion is None or not self._respuesta_activa:
            return
        try:
            await self._conexion.send({"type": "response.cancel"})
        except Exception:
            return

    async def _precalentar(self) -> None:
        """Evita que la primera frase real pague el arranque en frío."""
        if self._conexion is None:
            return
        await self._conexion.send({
            "type": "response.create",
            "response": {
                "conversation": "none",
                "metadata": {"purpose": "warmup"},
                "output_modalities": ["text"],
                "instructions": "Responde únicamente OK.",
            },
        })
        await self._esperar("response.done")

    async def _esperar(self, esperado: str) -> Any:
        while True:
            evento = await self._conexion.recv()
            if evento.type == "error":
                raise ErrorRealtimePrueba(str(evento.error))
            if evento.type == esperado:
                return evento
