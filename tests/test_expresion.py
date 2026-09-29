from core.expresion import ParserExpresionVoz


def test_parser_separa_expresiones_abiertas_del_texto_visible() -> None:
    texto = []
    expresiones = []
    parser = ParserExpresionVoz(texto.append, expresiones.append)

    parser.agregar("[[voi")
    parser.agregar("ce:quietly relieved, warm and slightly amused]]Hola, ")
    parser.agregar("Jhony. [[voice:deeply empathetic, soft, unhurried]]Lo siento.")
    parser.finalizar()

    assert "".join(texto) == "Hola, Jhony. Lo siento."
    assert expresiones == [
        "quietly relieved, warm and slightly amused",
        "deeply empathetic, soft, unhurried",
    ]


def test_parser_no_publica_una_marca_incompleta() -> None:
    texto = []
    parser = ParserExpresionVoz(texto.append)

    parser.agregar("Respuesta visible. [[voice:malformed")
    parser.finalizar()

    assert "".join(texto) == "Respuesta visible. "


def test_parser_conserva_corchetes_normales() -> None:
    texto = []
    parser = ParserExpresionVoz(texto.append)

    parser.agregar("Usa la lista [uno, dos] sin cambios.")
    parser.finalizar()

    assert "".join(texto) == "Usa la lista [uno, dos] sin cambios."
