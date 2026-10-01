import pytest

from core.enrutador_modelo import usar_modelo_rapido


@pytest.mark.parametrize(
    "texto",
    [
        "Hola, ¿cómo estás?",
        "Cuéntame algo interesante",
        "Tengo una buena noticia",
    ],
)
def test_conversacion_breve_usa_modelo_rapido(texto: str) -> None:
    assert usar_modelo_rapido(texto, 240) is True


@pytest.mark.parametrize(
    "texto",
    [
        "Calcula 40 + 2",
        "Haz una transferencia bancaria",
        "Busca las noticias de hoy",
        "Analiza este contrato y luego prepara un informe",
        "Abre la cámara de la entrada",
    ],
)
def test_herramientas_riesgo_y_complejidad_usan_astra(texto: str) -> None:
    assert usar_modelo_rapido(texto, 240) is False


def test_turno_posterior_a_herramienta_conserva_astra() -> None:
    assert usar_modelo_rapido("Gracias", 240, ("calcular",)) is False


def test_continuacion_de_peticion_compleja_conserva_astra() -> None:
    assert usar_modelo_rapido(
        "Continúa",
        240,
        pregunta_anterior="Analiza este contrato",
    ) is False
