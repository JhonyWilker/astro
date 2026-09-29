import wave
from pathlib import Path

from voice.grabar_muestras import BLOQUES, Bloque, Sesion, crear_pitido


class VozFalsa:
    def __init__(self):
        self.textos = []

    def synthesize_wav(self, texto, archivo, syn_config=None):
        self.textos.append(texto)
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(22050)
        archivo.writeframes(b"\x00\x00" * 2205)


class FlujoSalidaFalso:
    def __init__(self, registro):
        self.registro = registro

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback):
        return None

    def write(self, datos):
        self.registro.append(len(datos))
        return False


class FlujoEntradaFalso:
    def read(self, cantidad):
        return b"\x01\x00" * cantidad, False

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traceback):
        return None


class AudioFalso:
    def __init__(self):
        self.escrituras = []
        self.entradas = []

    def RawOutputStream(self, **opciones):
        return FlujoSalidaFalso(self.escrituras)

    def RawInputStream(self, **opciones):
        self.entradas.append(opciones)
        return FlujoEntradaFalso()


def crear_sesion(tmp_path: Path, voz: VozFalsa, audio: AudioFalso) -> Sesion:
    return Sesion(
        audio,
        voz,
        object(),
        microfono=1,
        altavoz=None,
        carpeta=tmp_path,
        esperar=lambda segundos: None,
    )


def test_el_pitido_dura_una_fraccion_de_segundo() -> None:
    assert len(crear_pitido()) == 2 * int(16000 * 0.15)


def test_cada_bloque_guarda_sus_muestras_en_su_carpeta(tmp_path: Path) -> None:
    voz = VozFalsa()
    audio = AudioFalso()
    bloques = (
        Bloque("positivas/normal", "Di Astro.", 3, 0.5),
        Bloque("negativas/parecidas", "Repite.", 1, 0.5, ("rastro", "hasta")),
    )

    grabadas = crear_sesion(tmp_path, voz, audio).ejecutar(bloques)

    assert grabadas == 5
    assert len(list((tmp_path / "positivas" / "normal").glob("*.wav"))) == 3
    parecidas = sorted((tmp_path / "negativas" / "parecidas").glob("*.wav"))
    assert [ruta.name for ruta in parecidas] == [
        "parecidas_001.wav",
        "parecidas_002.wav",
    ]
    assert "rastro" in voz.textos and "hasta" in voz.textos
    with wave.open(str(parecidas[0])) as archivo:
        assert archivo.getframerate() == 16000
        assert archivo.getnchannels() == 1
        assert archivo.getnframes() == 8000
    assert all(opciones["device"] == 1 for opciones in audio.entradas)


def test_el_plan_completo_pide_las_muestras_necesarias() -> None:
    positivas = sum(
        bloque.repeticiones
        for bloque in BLOQUES
        if bloque.carpeta.startswith("positivas")
    )
    negativas = {bloque.carpeta for bloque in BLOQUES if "negativas" in bloque.carpeta}

    assert positivas == 55
    assert {"negativas/libre_1", "negativas/parecidas"} <= negativas
