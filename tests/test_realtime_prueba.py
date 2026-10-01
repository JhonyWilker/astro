import asyncio
from pathlib import Path
from types import SimpleNamespace
import wave

from voice.realtime_prueba import SesionRealtimePrueba, leer_pcm_24khz


class ConexionFalsa:
    def __init__(self):
        self.enviados = []
        self.eventos = [
            SimpleNamespace(type="session.updated"),
            SimpleNamespace(type="response.done"),
            SimpleNamespace(type="response.output_text.delta", delta="Hola, "),
            SimpleNamespace(type="response.output_text.delta", delta="Jhony."),
            SimpleNamespace(type="response.done"),
        ]

    async def send(self, evento):
        self.enviados.append(evento)

    async def recv(self):
        return self.eventos.pop(0)


class GestorFalso:
    def __init__(self, conexion):
        self.conexion = conexion
        self.cerrado = False

    async def __aenter__(self):
        return self.conexion

    async def __aexit__(self, *_args):
        self.cerrado = True


class ClienteFalso:
    def __init__(self, conexion):
        gestor = GestorFalso(conexion)
        self.gestor = gestor
        self.realtime = SimpleNamespace(connect=lambda **_opciones: gestor)


def crear_wav(ruta: Path, frecuencia: int = 16000) -> None:
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(b"\x01\x00" * frecuencia)


def test_pcm_se_remuestrea_a_24khz(tmp_path: Path) -> None:
    ruta = tmp_path / "entrada.wav"
    crear_wav(ruta)

    pcm = leer_pcm_24khz(ruta)

    assert len(pcm) == 24000 * 2


def test_sesion_realtime_envia_audio_y_publica_texto(tmp_path: Path) -> None:
    ruta = tmp_path / "entrada.wav"
    crear_wav(ruta, 24000)
    conexion = ConexionFalsa()
    cliente = ClienteFalso(conexion)
    recibidos = []

    async def ejecutar():
        async with SesionRealtimePrueba(
            "Instrucciones de prueba",
            cliente=cliente,
        ) as sesion:
            return await sesion.responder(ruta, recibidos.append)

    resultado = asyncio.run(ejecutar())

    assert resultado.texto == "Hola, Jhony."
    assert resultado.ordenar_silencio is False
    assert recibidos == ["Hola, ", "Jhony."]
    tipos = [evento["type"] for evento in conexion.enviados]
    assert tipos == [
        "session.update",
        "response.create",
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
        "response.create",
    ]
    herramienta = conexion.enviados[0]["session"]["tools"][0]
    assert herramienta["name"] == "dormir_astro"
    assert cliente.gestor.cerrado is True


def test_sesion_realtime_convierte_orden_de_silencio_en_control(
    tmp_path: Path,
) -> None:
    ruta = tmp_path / "entrada.wav"
    crear_wav(ruta, 24000)
    conexion = ConexionFalsa()
    conexion.eventos = [
        SimpleNamespace(type="session.updated"),
        SimpleNamespace(type="response.done"),
        SimpleNamespace(
            type="response.done",
            response=SimpleNamespace(output=[SimpleNamespace(
                type="function_call",
                name="dormir_astro",
                call_id="call_silencio",
            )]),
        ),
    ]
    cliente = ClienteFalso(conexion)
    recibidos = []

    async def ejecutar():
        async with SesionRealtimePrueba(
            "Instrucciones de prueba",
            cliente=cliente,
        ) as sesion:
            return await sesion.responder(ruta, recibidos.append)

    resultado = asyncio.run(ejecutar())

    assert resultado.texto == ""
    assert resultado.ordenar_silencio is True
    assert recibidos == []
    assert conexion.enviados[-1] == {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": "call_silencio",
            "output": '{"dormido":true}',
        },
    }
