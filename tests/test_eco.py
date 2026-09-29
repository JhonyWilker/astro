import numpy as np

from voice.eco import CanceladorEco, MUESTRAS_ECO


class ProcesadorFalso:
    def __init__(self):
        self.llamadas = []
        self.reinicios = 0

    def process(self, microfono, referencia):
        self.llamadas.append((microfono.copy(), referencia.copy()))
        return microfono - referencia

    def reset(self):
        self.reinicios += 1


def test_cancelador_aisla_el_procesador_nativo() -> None:
    procesador = ProcesadorFalso()
    cancelador = CanceladorEco(procesador=procesador)
    microfono = np.full(MUESTRAS_ECO, 5, dtype=np.int16)
    referencia = np.full(MUESTRAS_ECO, 2, dtype=np.int16)

    limpio = cancelador.procesar(microfono, referencia)
    cancelador.reiniciar()

    assert np.all(limpio == 3)
    assert np.array_equal(procesador.llamadas[0][0], microfono)
    assert np.array_equal(procesador.llamadas[0][1], referencia)
    assert procesador.reinicios == 1


def test_webrtc_atenua_un_eco_sintetico() -> None:
    cancelador = CanceladorEco(retardo_ms=40)
    rng = np.random.default_rng(34)
    referencia = rng.integers(
        -6000,
        6000,
        MUESTRAS_ECO * 100,
        dtype=np.int16,
    )
    eco = np.concatenate((
        np.zeros(MUESTRAS_ECO * 4, dtype=np.int16),
        referencia,
    ))[:len(referencia)]
    limpio = []

    for inicio in range(0, len(referencia), MUESTRAS_ECO):
        limpio.append(cancelador.procesar(
            eco[inicio:inicio + MUESTRAS_ECO],
            referencia[inicio:inicio + MUESTRAS_ECO],
        ))

    limpio = np.concatenate(limpio)
    rms_eco = np.sqrt(np.mean(eco.astype(np.float64) ** 2))
    rms_limpio = np.sqrt(np.mean(limpio.astype(np.float64) ** 2))
    assert rms_limpio < rms_eco * 0.2
