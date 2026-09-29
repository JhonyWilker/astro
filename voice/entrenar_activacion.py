"""Entrena el modelo de activación de «Astro» con tu voz, voces sintéticas y habla real.

Los modelos de openWakeWord (melspectrogram y embedding) convierten el audio
en huellas de 96 números por cada 80 ms. Sobre las últimas 16 huellas
(1,28 s) se entrena un clasificador pequeño que dice si la palabra acaba de
pronunciarse. El resultado es un archivo .npz sin dependencias pesadas.

El entrenamiento usa minado de negativas difíciles: se entrena, se buscan las
ventanas de habla que engañan al modelo, se añaden y se vuelve a entrenar.
"""

import json
import random
import re
import wave
import zipfile
from argparse import ArgumentParser
from dataclasses import dataclass
from itertools import count
from math import gcd
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from scipy.signal import fftconvolve, resample_poly

from voice.activacion import (
    FRECUENCIA_HZ,
    MUESTRAS_ACTIVACION,
    SEGUNDOS_BLOQUE_ACTIVACION,
)
from voice.generar_sinteticos import CARPETA_SINTETICOS, es_validacion_sintetica
from voice.vad_silero import (
    MUESTRAS_BLOQUE as MUESTRAS_VAD,
    RAIZ_PROYECTO,
    RUTA_MODELOS_ACTIVACION,
    VadSilero,
)


CARPETA_DATOS = RAIZ_PROYECTO / "data" / "wakeword"
CARPETA_MUESTRAS = CARPETA_DATOS / "muestras"
CARPETA_CORPUS = CARPETA_DATOS / "corpus"
RUTA_CARACTERISTICAS = CARPETA_DATOS / "caracteristicas.npz"
RUTA_BANCO = CARPETA_DATOS / "banco_negativo.npy"
RUTA_FLUJO_VALIDACION = CARPETA_DATOS / "flujo_negativo_validacion.npy"
RUTA_RESERVADAS = CARPETA_DATOS / "reservadas.json"
RUTA_MODELO_ASTRO = RUTA_MODELOS_ACTIVACION / "astro_v1.npz"
RUTA_AJUSTES_ASTRO = RUTA_MODELOS_ACTIVACION / "astro_v1.json"
FRAMES_VENTANA = 16
CHUNKS_CALENTAMIENTO = 12
ZONA_POSITIVA = (0.08, 0.32)
ZONA_IGNORADA = (-0.5, 1.3)
PESO_USUARIO = 3.0
UMBRAL_VOZ_MUESTRAS = 0.35
PESO_EXTRANJERA = 0.5


def peso_sintetica(nombre_archivo: str) -> float:
    """Las voces de otros idiomas aportan variedad, pero pronuncian «Astro» a su manera."""
    return PESO_EXTRANJERA if nombre_archivo.startswith(("en_US-", "de_DE-")) else 1.0


def cargar_wav16(origen: Path | BinaryIO) -> np.ndarray:
    entrada = str(origen) if isinstance(origen, Path) else origen
    with wave.open(entrada, "rb") as archivo:
        frecuencia = archivo.getframerate()
        canales = archivo.getnchannels()
        audio = np.frombuffer(
            archivo.readframes(archivo.getnframes()), dtype=np.int16
        )
    if canales > 1:
        audio = audio.reshape(-1, canales)[:, 0]
    if frecuencia != FRECUENCIA_HZ:
        divisor = gcd(frecuencia, FRECUENCIA_HZ)
        audio = resample_poly(
            audio.astype(np.float32),
            FRECUENCIA_HZ // divisor,
            frecuencia // divisor,
        )
    return np.clip(audio, -32768, 32767).astype(np.int16)


def probabilidades_voz(audio: np.ndarray, vad: VadSilero) -> np.ndarray:
    vad.reiniciar()
    bloques = len(audio) // MUESTRAS_VAD
    return np.array(
        [
            vad.probabilidad(audio[i * MUESTRAS_VAD:(i + 1) * MUESTRAS_VAD])
            for i in range(bloques)
        ]
    )


def fin_de_habla(
    audio: np.ndarray,
    vad: VadSilero,
    umbral: float = 0.5,
) -> float | None:
    """Segundo en el que termina la última voz del clip."""
    con_voz = np.flatnonzero(probabilidades_voz(audio, vad) >= umbral)
    if len(con_voz) < 2:
        return None
    return float((con_voz[-1] + 1) * MUESTRAS_VAD / FRECUENCIA_HZ)


def fin_primera_palabra(ruta: Path, modelo_whisper) -> float | None:
    segmentos, _ = modelo_whisper.transcribe(
        str(ruta), language="es", word_timestamps=True
    )
    for segmento in segmentos:
        if segmento.words:
            return float(segmento.words[0].end)
    return None


class Aumentador:
    """Añade fondo, ganancia y reverberación a un clip."""

    def __init__(
        self,
        aleatorio: np.random.Generator,
        habla_fondo: list[np.ndarray],
        sala: list[np.ndarray],
    ) -> None:
        self.aleatorio = aleatorio
        self.habla_fondo = habla_fondo
        self.sala = sala

    def _fondo(self, longitud: int) -> np.ndarray:
        tipo = self.aleatorio.choice(["blanco", "rosa", "sala", "habla", "habla"])
        if tipo == "sala" and self.sala:
            origen = self.sala[self.aleatorio.integers(len(self.sala))]
        elif tipo == "habla" and self.habla_fondo:
            origen = self.habla_fondo[self.aleatorio.integers(len(self.habla_fondo))]
        elif tipo == "rosa":
            ruido = self.aleatorio.normal(0, 1, longitud + 1000)
            origen = np.cumsum(ruido)
            origen = origen - np.convolve(origen, np.ones(800) / 800, "same")
            origen = origen.astype(np.float32)
        else:
            origen = self.aleatorio.normal(0, 1, longitud).astype(np.float32)
        origen = origen.astype(np.float32)
        if len(origen) < longitud:
            origen = np.tile(origen, longitud // len(origen) + 1)
        inicio = int(self.aleatorio.integers(0, len(origen) - longitud + 1))
        return origen[inicio:inicio + longitud]

    def _reverberacion(self, clip: np.ndarray) -> np.ndarray:
        rt60 = self.aleatorio.uniform(0.15, 0.6)
        muestras = int(0.5 * FRECUENCIA_HZ)
        instantes = np.arange(muestras) / FRECUENCIA_HZ
        respuesta = self.aleatorio.normal(0, 1, muestras) * np.exp(
            -6.9 * instantes / rt60
        )
        respuesta[0] = 1.0
        respuesta /= np.sqrt(np.sum(respuesta**2))
        return fftconvolve(clip, respuesta)[: len(clip)].astype(np.float32)

    def componer(
        self,
        clip: np.ndarray,
        fin_clip: float | None,
        con_pausas: bool = True,
        aumentar: bool = True,
    ) -> tuple[np.ndarray, float | None]:
        if aumentar and self.aleatorio.random() < 0.8:
            # Cambio de velocidad y tono: simula otros hablantes.
            factor = self.aleatorio.uniform(0.88, 1.14)
            arriba = int(round(100 / factor))
            clip = resample_poly(clip.astype(np.float32), arriba, 100)
            if fin_clip is not None:
                fin_clip *= arriba / 100
        previo = self.aleatorio.uniform(1.0, 2.0) if con_pausas else 0.5
        posterior = self.aleatorio.uniform(1.4, 2.0) if con_pausas else 0.5
        señal = np.concatenate(
            (
                np.zeros(int(previo * FRECUENCIA_HZ), dtype=np.float32),
                clip.astype(np.float32),
                np.zeros(int(posterior * FRECUENCIA_HZ), dtype=np.float32),
            )
        )
        if aumentar:
            centro = slice(
                int(previo * FRECUENCIA_HZ),
                int(previo * FRECUENCIA_HZ) + len(clip),
            )
            if self.aleatorio.random() < 0.35:
                señal[centro] = self._reverberacion(señal[centro])
            ganancia = 10 ** (self.aleatorio.uniform(-34, 3) / 20)
            señal *= ganancia
            potencia = float(np.sqrt(np.mean(señal[centro] ** 2))) + 1.0
            fondo = self._fondo(len(señal))
            fondo = fondo / (float(np.sqrt(np.mean(fondo**2))) + 1e-6)
            if self.aleatorio.random() < 0.85:
                relacion = self.aleatorio.uniform(4, 30)
                señal += fondo * potencia / (10 ** (relacion / 20))
            señal += self.aleatorio.normal(
                0, self.aleatorio.uniform(0, 8), len(señal)
            )
        señal = np.clip(señal, -32768, 32767).astype(np.int16)
        fin = None if fin_clip is None else previo + fin_clip
        return señal, fin


class Extractor:
    def __init__(self) -> None:
        from openwakeword.utils import AudioFeatures

        self._af = AudioFeatures(
            melspec_model_path=str(RUTA_MODELOS_ACTIVACION / "melspectrogram.onnx"),
            embedding_model_path=str(RUTA_MODELOS_ACTIVACION / "embedding_model.onnx"),
        )

    def ventanas(self, señal: np.ndarray) -> np.ndarray:
        """Una fila de 1536 números por cada bloque de 80 ms."""
        self._af.reset()
        filas = []
        for inicio in range(0, len(señal) - MUESTRAS_ACTIVACION + 1, MUESTRAS_ACTIVACION):
            self._af(señal[inicio:inicio + MUESTRAS_ACTIVACION])
            filas.append(self._af.get_features(FRAMES_VENTANA)[0].reshape(-1))
        return np.array(filas, dtype=np.float32)


def etiquetar(cantidad: int, fin: float | None) -> np.ndarray:
    """1 positiva, 0 negativa y -1 zona ambigua que se descarta."""
    etiquetas = np.zeros(cantidad, dtype=np.int8)
    etiquetas[:CHUNKS_CALENTAMIENTO] = -1
    if fin is None:
        return etiquetas
    for indice in range(CHUNKS_CALENTAMIENTO, cantidad):
        distancia = (indice + 1) * SEGUNDOS_BLOQUE_ACTIVACION - fin
        if ZONA_POSITIVA[0] <= distancia <= ZONA_POSITIVA[1]:
            etiquetas[indice] = 1
        elif ZONA_IGNORADA[0] <= distancia <= ZONA_IGNORADA[1]:
            etiquetas[indice] = -1
    return etiquetas


class Coleccion:
    """Ventanas de un tipo (positivas o negativas) con su peso, origen y clip."""

    def __init__(self, tipo_float: Any = np.float32) -> None:
        self.tipo_float = tipo_float
        self.x: list[np.ndarray] = []
        self.peso: list[float] = []
        self.origen: list[str] = []
        self.grupo: list[int] = []

    def añadir(
        self,
        filas: np.ndarray,
        indices,
        peso: float,
        origen: str,
        grupo: int = -1,
    ) -> None:
        indices = np.asarray(indices, dtype=int)
        if not len(indices):
            return
        self.x.append(filas[indices].astype(self.tipo_float))
        self.peso.extend([peso] * len(indices))
        self.origen.extend([origen] * len(indices))
        self.grupo.extend([grupo] * len(indices))

    def empaquetar(self) -> dict[str, np.ndarray]:
        dimension = self.x[0].shape[1] if self.x else 1536
        return {
            "x": (
                np.concatenate(self.x)
                if self.x
                else np.empty((0, dimension), dtype=self.tipo_float)
            ),
            "peso": np.array(self.peso, dtype=np.float32),
            "origen": np.array(self.origen),
            "grupo": np.array(self.grupo, dtype=np.int32),
        }


def listar_wav(carpeta: Path) -> list[Path]:
    return sorted(carpeta.rglob("*.wav")) if carpeta.is_dir() else []


def listar_corpus_real(
    carpeta: Path,
    azar: random.Random,
    max_entrenamiento: int = 1200,
    max_validacion: int = 250,
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    """Enunciados de habla real, separando hablantes para entrenar y validar."""
    entrenamiento: list[tuple[Path, str]] = []
    validacion: list[tuple[Path, str]] = []
    for ruta_zip in sorted(carpeta.glob("*.zip")):
        try:
            with zipfile.ZipFile(ruta_zip) as contenido:
                miembros = [n for n in contenido.namelist() if n.lower().endswith(".wav")]
        except zipfile.BadZipFile:
            continue
        por_hablante: dict[str, list[str]] = {}
        for nombre in miembros:
            partes = Path(nombre).stem.split("_")
            hablante = partes[1] if len(partes) >= 3 else partes[0]
            por_hablante.setdefault(hablante, []).append(nombre)
        hablantes = sorted(por_hablante)
        azar.shuffle(hablantes)
        reservados = set(hablantes[: max(1, len(hablantes) // 8)])
        propios = [(ruta_zip, n) for h in hablantes if h not in reservados for n in por_hablante[h]]
        ajenos = [(ruta_zip, n) for h in reservados for n in por_hablante[h]]
        azar.shuffle(propios)
        azar.shuffle(ajenos)
        entrenamiento += propios[:max_entrenamiento]
        validacion += ajenos[:max_validacion]
    return entrenamiento, validacion


def cargar_enunciado(zip_y_nombre: tuple[Path, str]) -> np.ndarray:
    ruta_zip, nombre = zip_y_nombre
    with zipfile.ZipFile(ruta_zip) as contenido, contenido.open(nombre) as archivo:
        return cargar_wav16(archivo)


def preparar_datos(semilla: int = 29, progreso=print) -> Path:
    aleatorio = np.random.default_rng(semilla)
    azar = random.Random(semilla)
    vad = VadSilero()
    extractor = Extractor()

    positivas_usuario = listar_wav(CARPETA_MUESTRAS / "positivas")
    libres = listar_wav(CARPETA_MUESTRAS / "negativas" / "libre_1") + listar_wav(
        CARPETA_MUESTRAS / "negativas" / "libre_2"
    )
    parecidas = listar_wav(CARPETA_MUESTRAS / "negativas" / "parecidas")
    silencios = listar_wav(CARPETA_MUESTRAS / "negativas" / "silencio")
    if not positivas_usuario:
        raise FileNotFoundError("No hay muestras positivas en " + str(CARPETA_MUESTRAS))

    sinteticas_neg = listar_wav(CARPETA_SINTETICOS / "negativas")
    sinteticas_pos = listar_wav(CARPETA_SINTETICOS / "positivas")
    sinteticas_continuas = listar_wav(CARPETA_SINTETICOS / "positivas_continuas")
    real_entrenamiento, real_validacion = listar_corpus_real(CARPETA_CORPUS, azar)
    progreso(
        f"Habla real: {len(real_entrenamiento)} enunciados para entrenar, "
        f"{len(real_validacion)} de hablantes ajenos para validar"
    )

    habla_fondo = [cargar_wav16(r).astype(np.float32) for r in libres]
    sala = [cargar_wav16(r).astype(np.float32) for r in silencios]
    fondo_tv = [cargar_wav16(r).astype(np.float32) for r in azar.sample(sinteticas_neg, min(60, len(sinteticas_neg)))]
    habla_fondo += [np.concatenate(fondo_tv[i:i + 8]) for i in range(0, len(fondo_tv) - 7, 8)]
    for elemento in azar.sample(real_entrenamiento, min(40, len(real_entrenamiento))):
        habla_fondo.append(cargar_enunciado(elemento).astype(np.float32))
    aumentador = Aumentador(aleatorio, habla_fondo, sala)

    from voice.transcribir import cargar_modelo

    whisper = cargar_modelo()

    positivas = Coleccion()
    positivas_validacion = Coleccion()
    banco = Coleccion(np.float16)
    grupos = count()
    flujos_validacion: list[np.ndarray] = []

    def añadir_positiva(destino, audio, fin, peso, origen, copias, con_aumento=True):
        for _ in range(copias):
            señal, fin_total = aumentador.componer(audio, fin, aumentar=con_aumento)
            filas = extractor.ventanas(señal)
            etiquetas = etiquetar(len(filas), fin_total)
            destino.añadir(filas, np.flatnonzero(etiquetas == 1), peso, origen, next(grupos))
            contexto = np.flatnonzero(etiquetas == 0)
            if len(contexto) > 3:
                contexto = aleatorio.choice(contexto, 3, replace=False)
            banco.añadir(filas, contexto, peso, "contexto_pos")

    def añadir_negativa(audio, peso, origen, copias=1, salto=1):
        for _ in range(copias):
            señal, _ = aumentador.componer(audio, None, con_pausas=False)
            filas = extractor.ventanas(señal)
            libres_ = np.flatnonzero(etiquetar(len(filas), None) == 0)[::salto]
            banco.añadir(filas, libres_, peso, origen)

    # ---- positivas del usuario (20 % para validar, por clip) -------------
    reservadas = set(azar.sample(positivas_usuario, max(6, len(positivas_usuario) // 5)))
    RUTA_RESERVADAS.write_text(
        json.dumps(sorted(str(r.relative_to(CARPETA_MUESTRAS)) for r in reservadas), indent=2),
        encoding="utf-8",
    )
    descartadas = 0
    for ruta in positivas_usuario:
        audio = cargar_wav16(ruta)
        if ruta.parent.name == "frase":
            fin = fin_primera_palabra(ruta, whisper)
        else:
            fin = fin_de_habla(audio, vad, UMBRAL_VOZ_MUESTRAS)
        if fin is None or float(probabilidades_voz(audio, vad).max()) < UMBRAL_VOZ_MUESTRAS:
            descartadas += 1
            continue
        if ruta in reservadas:
            añadir_positiva(positivas_validacion, audio, fin, PESO_USUARIO, "usuario_pos", 4, aleatorio.random() < 0.5)
        else:
            añadir_positiva(positivas, audio, fin, PESO_USUARIO, "usuario_pos", 40)
    progreso(f"Positivas del usuario: {len(positivas_usuario) - descartadas} útiles, {descartadas} descartadas")

    # ---- negativas del usuario --------------------------------------------
    for ruta in libres:
        audio = cargar_wav16(ruta)
        corte = max(0, len(audio) - 25 * FRECUENCIA_HZ)
        flujos_validacion.append(audio[corte:])
        añadir_negativa(audio[:corte], PESO_USUARIO / 3, "usuario_neg", copias=4)
    for ruta in parecidas + silencios:
        añadir_negativa(cargar_wav16(ruta), PESO_USUARIO, "usuario_neg", copias=6)
    progreso("Negativas del usuario listas")

    # ---- sintéticas -------------------------------------------------------
    for indice, ruta in enumerate(sinteticas_pos):
        audio = cargar_wav16(ruta)
        fin = fin_de_habla(audio, vad)
        if fin is None:
            continue
        if es_validacion_sintetica(ruta.name):
            añadir_positiva(positivas_validacion, audio, fin, 1.0, "sint_pos", 1)
        else:
            añadir_positiva(positivas, audio, fin, peso_sintetica(ruta.name), "sint_pos", 5)
    for ruta in sinteticas_continuas:
        coincidencia = re.search(r"_fin(\d+)ms", ruta.name)
        if coincidencia is None:
            continue
        audio = cargar_wav16(ruta)
        fin = int(coincidencia.group(1)) / 1000
        if es_validacion_sintetica(ruta.name):
            añadir_positiva(positivas_validacion, audio, fin, 1.0, "cont_pos", 1)
        else:
            añadir_positiva(positivas, audio, fin, peso_sintetica(ruta.name), "cont_pos", 6)
    progreso("Sintéticas positivas listas")
    for indice, ruta in enumerate(sinteticas_neg):
        audio = cargar_wav16(ruta)
        if es_validacion_sintetica(ruta.name):
            flujos_validacion.append(audio)
            continue
        añadir_negativa(audio, peso_sintetica(ruta.name), "sint_neg", copias=2)
        if indice % 500 == 0:
            progreso(f"  sintéticas negativas {indice}/{len(sinteticas_neg)}")

    # ---- habla real ---------------------------------------------------------
    for indice, elemento in enumerate(real_entrenamiento):
        añadir_negativa(cargar_enunciado(elemento), 1.0, "real_neg", copias=1, salto=2)
        if indice % 300 == 0:
            progreso(f"  habla real {indice}/{len(real_entrenamiento)}")
    for elemento in real_validacion:
        flujos_validacion.append(cargar_enunciado(elemento))

    ent = positivas.empaquetar()
    val = positivas_validacion.empaquetar()
    neg = banco.empaquetar()
    RUTA_CARACTERISTICAS.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        RUTA_CARACTERISTICAS,
        **{f"ent_{k}": v for k, v in ent.items()},
        **{f"val_{k}": v for k, v in val.items()},
        banco_peso=neg["peso"],
        banco_origen=neg["origen"],
    )
    np.save(RUTA_BANCO, neg["x"])
    flujo = np.concatenate(
        [np.concatenate((f, np.zeros(FRECUENCIA_HZ, dtype=np.int16))) for f in flujos_validacion]
    )
    np.save(RUTA_FLUJO_VALIDACION, flujo)
    progreso(
        f"Positivas: {len(ent['x'])} entrenamiento, {len(val['x'])} validación. "
        f"Banco de negativas: {len(neg['x'])} ventanas. "
        f"Flujo negativo de validación: {len(flujo) / FRECUENCIA_HZ / 60:.1f} min"
    )
    return RUTA_CARACTERISTICAS


RUTA_EXTRA = CARPETA_DATOS / "extra_negativas.npz"
RUTA_FLUJO_CONFUSAS = CARPETA_DATOS / "flujo_confusas_validacion.npy"
RUTA_FLUJO_REAL = CARPETA_DATOS / "flujo_real_validacion.npy"


def preparar_extra(semilla: int = 31, progreso=print) -> Path:
    """Negativas parecidas a «Astro» (astronauta, castro...) que siempre entran en el entrenamiento.

    Reserva una voz y el 20 % de tus clips para medir después si se corrigió.
    """
    aleatorio = np.random.default_rng(semilla)
    azar = random.Random(semilla)
    extractor = Extractor()
    libres = listar_wav(CARPETA_MUESTRAS / "negativas" / "libre_1") + listar_wav(
        CARPETA_MUESTRAS / "negativas" / "libre_2"
    )
    silencios = listar_wav(CARPETA_MUESTRAS / "negativas" / "silencio")
    habla_fondo = [cargar_wav16(r).astype(np.float32) for r in libres]
    habla_fondo += [
        cargar_enunciado(e).astype(np.float32)
        for e in azar.sample(
            (listar_corpus_real(CARPETA_CORPUS, random.Random(29))[0]), 40
        )
    ]
    sala = [cargar_wav16(r).astype(np.float32) for r in silencios]
    aumentador = Aumentador(aleatorio, habla_fondo, sala)

    coleccion = Coleccion(np.float16)
    flujos: list[np.ndarray] = []
    silencio = np.zeros(FRECUENCIA_HZ, dtype=np.int16)

    def añadir(audio: np.ndarray, peso: float, origen: str, copias: int) -> None:
        for _ in range(copias):
            señal, _ = aumentador.componer(audio, None, con_pausas=False)
            filas = extractor.ventanas(señal)
            libres_ = np.flatnonzero(etiquetar(len(filas), None) == 0)[::2]
            coleccion.añadir(filas, libres_, peso, origen)

    usuario = listar_wav(CARPETA_MUESTRAS / "negativas_extra")
    reservadas = set(azar.sample(usuario, max(1, len(usuario) // 5))) if usuario else set()
    for ruta in usuario:
        audio = cargar_wav16(ruta)
        if ruta in reservadas:
            flujos.append(np.concatenate((audio, silencio)))
        else:
            añadir(audio, PESO_USUARIO * 2, "extra_usuario", 10)
    progreso(f"Tus palabras parecidas: {len(usuario) - len(reservadas)} para entrenar, {len(reservadas)} reservadas")

    sinteticas = listar_wav(CARPETA_SINTETICOS / "negativas_confusas")
    for indice, ruta in enumerate(sinteticas):
        audio = cargar_wav16(ruta)
        if es_validacion_sintetica(ruta.name):
            flujos.append(np.concatenate((audio, silencio)))
        else:
            añadir(audio, 1.5, "extra_sintetica", 2)
        if indice % 300 == 0:
            progreso(f"  sintéticas parecidas {indice}/{len(sinteticas)}")

    extra = coleccion.empaquetar()
    np.savez_compressed(RUTA_EXTRA, x=extra["x"], peso=extra["peso"])
    if flujos:
        np.save(RUTA_FLUJO_CONFUSAS, np.concatenate(flujos))
    progreso(
        f"Extra: {len(extra['x'])} ventanas negativas. "
        f"Flujo de validación de palabras parecidas: "
        f"{sum(len(f) for f in flujos) / FRECUENCIA_HZ:.0f} s"
    )
    return RUTA_EXTRA


def construir_flujo_real(maximo_por_corpus: int = 900) -> np.ndarray:
    """Habla española real de hablantes ajenos más tu habla libre: la referencia de falsas activaciones."""
    if RUTA_FLUJO_REAL.is_file():
        return np.load(RUTA_FLUJO_REAL)
    azar = random.Random(29)
    _, ajenos = listar_corpus_real(CARPETA_CORPUS, azar, max_validacion=maximo_por_corpus)
    silencio = np.zeros(FRECUENCIA_HZ, dtype=np.int16)
    partes = [np.concatenate((cargar_enunciado(elemento), silencio)) for elemento in ajenos]
    libres = listar_wav(CARPETA_MUESTRAS / "negativas" / "libre_1") + listar_wav(
        CARPETA_MUESTRAS / "negativas" / "libre_2"
    )
    for ruta in libres:
        partes.append(np.concatenate((cargar_wav16(ruta)[-25 * FRECUENCIA_HZ:], silencio)))
    flujo = np.concatenate(partes)
    np.save(RUTA_FLUJO_REAL, flujo)
    return flujo


UMBRALES = (0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.98)
CHUNKS_DESCANSO = 25


def disparos(puntuaciones: np.ndarray, umbral: float, consecutivos: int = 1) -> int:
    """Cuenta activaciones aplicando el descanso de 2 s del detector."""
    total = 0
    descanso = 0
    seguidas = 0
    for valor in puntuaciones:
        if descanso > 0:
            descanso -= 1
            seguidas = 0
            continue
        seguidas = seguidas + 1 if valor >= umbral else 0
        if seguidas >= consecutivos:
            total += 1
            descanso = CHUNKS_DESCANSO
            seguidas = 0
    return total


def puntuar_por_lotes(capas, media, escala, filas: np.ndarray, lote: int = 20000) -> np.ndarray:
    from voice.modelo_astro import reenviar

    return np.concatenate(
        [
            reenviar(capas, media, escala, filas[i:i + lote].astype(np.float32))
            for i in range(0, len(filas), lote)
        ]
    )


def entrenar(
    ruta_caracteristicas: Path = RUTA_CARACTERISTICAS,
    ruta_salida: Path = RUTA_MODELO_ASTRO,
    neuronas: int = 64,
    rondas: int = 3,
    proporcion_positivas: float = 0.5,
    penalizacion: float = 1e-3,
    iteraciones: int = 120,
    escribir_ajustes: bool = True,
    progreso=print,
) -> dict:
    from sklearn.neural_network import MLPClassifier

    from voice.modelo_astro import guardar_modelo

    datos = np.load(ruta_caracteristicas)
    banco = np.load(RUTA_BANCO, mmap_mode="r")
    positivas_x = datos["ent_x"].astype(np.float32)
    positivas_peso = datos["ent_peso"]
    banco_peso = datos["banco_peso"]
    aleatorio = np.random.default_rng(0)

    extra_x = np.empty((0, positivas_x.shape[1]), dtype=np.float32)
    extra_peso = np.empty(0, dtype=np.float32)
    if RUTA_EXTRA.is_file():
        extra = np.load(RUTA_EXTRA)
        extra_x = extra["x"].astype(np.float32)
        extra_peso = extra["peso"]
        progreso(f"Negativas extra obligatorias: {len(extra_x)} ventanas")

    inicial = aleatorio.choice(len(banco), min(35000, len(banco)), replace=False)
    usadas = set(int(i) for i in inicial)
    media = np.concatenate((positivas_x, np.asarray(banco[sorted(usadas)], dtype=np.float32))).mean(axis=0)
    escala = (
        np.concatenate((positivas_x, np.asarray(banco[sorted(usadas)], dtype=np.float32))).std(axis=0) + 1e-6
    )

    capas = []
    for ronda in range(rondas):
        indices = np.array(sorted(usadas))
        negativas_x = np.concatenate(
            (np.asarray(banco[indices], dtype=np.float32), extra_x)
        )
        x = np.concatenate((positivas_x, negativas_x))
        y = np.concatenate((np.ones(len(positivas_x)), np.zeros(len(negativas_x))))
        peso = np.concatenate(
            (positivas_peso, banco_peso[indices], extra_peso)
        ).astype(np.float64)
        peso[y == 1] *= proporcion_positivas * peso[y == 0].sum() / peso[y == 1].sum()
        progreso(
            f"Ronda {ronda + 1}/{rondas}: {len(positivas_x)} positivas, "
            f"{len(negativas_x)} negativas..."
        )
        red = MLPClassifier(
            hidden_layer_sizes=(neuronas,),
            alpha=penalizacion,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=6,
            max_iter=iteraciones,
            random_state=ronda,
        )
        red.fit((x - media) / escala, y, sample_weight=peso)
        capas = [
            (pesos.astype(np.float32), sesgos.astype(np.float32))
            for pesos, sesgos in zip(red.coefs_, red.intercepts_)
        ]
        if ronda < rondas - 1:
            puntuaciones = puntuar_por_lotes(capas, media, escala, banco)
            puntuaciones[list(usadas)] = -1
            orden = np.argsort(-puntuaciones)[:30000]
            nuevas = orden[puntuaciones[orden] >= 0.05]
            usadas.update(int(i) for i in nuevas)
            progreso(
                f"  minado: {len(nuevas)} negativas difíciles nuevas "
                f"(máxima puntuación {float(puntuaciones[orden[0]]):.2f})"
            )

    guardar_modelo(ruta_salida, capas, media.astype(np.float32), escala.astype(np.float32))
    progreso(f"Modelo guardado en {ruta_salida}")
    return evaluar(capas, media, escala, datos, escribir_ajustes, progreso)


def evaluar(capas, media, escala, datos, escribir_ajustes: bool = True, progreso=print) -> dict:
    vx = datos["val_x"]
    origen, grupo = datos["val_origen"], datos["val_grupo"]
    puntuaciones = puntuar_por_lotes(capas, media, escala, vx)

    flujo = construir_flujo_real()
    puntos_flujo = puntuar_por_lotes(capas, media, escala, Extractor().ventanas(flujo))
    horas = len(flujo) / FRECUENCIA_HZ / 3600

    resultado: dict = {}
    progreso("")
    progreso("umbral | tus frases | sintéticas | continuas | falsas/hora: 1 bloque · 2 seguidos")
    for umbral in UMBRALES:
        fila = []
        for nombre in ("usuario_pos", "sint_pos", "cont_pos"):
            grupos = np.unique(grupo[origen == nombre])
            acertadas = sum(bool((puntuaciones[grupo == g] >= umbral).any()) for g in grupos)
            fila.append((acertadas, len(grupos)))
        falsas = [disparos(puntos_flujo, umbral, c) / horas for c in (1, 2)]
        resultado[umbral] = (fila, falsas)
        columnas = "  |  ".join(
            f"{a:3d}/{n:<3d} ({100 * a / max(1, n):3.0f}%)" for a, n in fila
        )
        progreso(f" {umbral:4.2f}  |  {columnas}  |  {falsas[0]:6.1f} · {falsas[1]:6.1f}")
    progreso(
        f"(falsas/hora medidas sobre {horas * 60:.1f} min de habla española real de "
        "hablantes ajenos y tuya, sin «Astro» y sin filtro de voz)"
    )

    ajustes = elegir_ajustes(resultado)
    if escribir_ajustes:
        RUTA_AJUSTES_ASTRO.write_text(json.dumps(ajustes, indent=2), encoding="utf-8")
    progreso(f"Ajustes recomendados: {ajustes}")
    return resultado


def elegir_ajustes(resultado: dict, maximo_falsas_hora: float = 3.0) -> dict:
    """El umbral más sensible con pocas falsas activaciones; si no hay, el más exigente."""
    for consecutivos, indice in ((2, 1), (1, 0)):
        candidatos = [
            (umbral, fila)
            for umbral, (fila, falsas) in resultado.items()
            if falsas[indice] <= maximo_falsas_hora
        ]
        if candidatos:
            umbral, fila = min(candidatos, key=lambda c: c[0])
            return {
                "umbral": umbral,
                "bloques_consecutivos": consecutivos,
                "cumple_objetivo": True,
            }
    return {"umbral": max(UMBRALES), "bloques_consecutivos": 2, "cumple_objetivo": False}


def main() -> int:
    argumentos = ArgumentParser(description=__doc__)
    argumentos.add_argument("--semilla", type=int, default=29)
    argumentos.add_argument(
        "--paso",
        choices=("datos", "extra", "entrenar", "todo"),
        default="todo",
    )
    argumentos.add_argument("--neuronas", type=int, default=64)
    argumentos.add_argument("--rondas", type=int, default=3)
    argumentos.add_argument("--penalizacion", type=float, default=1e-3)
    argumentos.add_argument("--proporcion-positivas", type=float, default=0.5)
    argumentos.add_argument("--iteraciones", type=int, default=120)
    opciones = argumentos.parse_args()
    if opciones.paso in ("datos", "todo"):
        preparar_datos(opciones.semilla)
    if opciones.paso == "extra":
        preparar_extra()
    if opciones.paso in ("entrenar", "todo"):
        entrenar(
            neuronas=opciones.neuronas,
            rondas=opciones.rondas,
            proporcion_positivas=opciones.proporcion_positivas,
            penalizacion=opciones.penalizacion,
            iteraciones=opciones.iteraciones,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
