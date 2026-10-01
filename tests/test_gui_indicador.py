from gui.indicador import APARIENCIAS, apariencia_para


def test_todos_los_estados_de_la_fase_tienen_apariencia_propia() -> None:
    esperados = {
        "desconectado",
        "microfono_apagado",
        "dormido",
        "escuchando",
        "pensando",
        "ejecutando",
        "hablando",
    }

    assert set(APARIENCIAS) == esperados
    assert len({apariencia.color for apariencia in APARIENCIAS.values()}) == len(esperados)
    assert all(apariencia.texto for apariencia in APARIENCIAS.values())


def test_un_estado_desconocido_no_parece_un_microfono_apagado() -> None:
    assert apariencia_para("desconocido") == APARIENCIAS["desconectado"]
    assert apariencia_para(None) != APARIENCIAS["microfono_apagado"]

