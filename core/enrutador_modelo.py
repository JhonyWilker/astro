"""Selección determinista entre conversación rápida y razonamiento completo."""

import re
import unicodedata


PATRONES_ASTRA = tuple(map(re.compile, (
    r"\b(analiza|compara|demuestra|investiga|planifica|razona|resuelve)\b",
    r"\b(codigo|programa|arquitectura|ecuacion|informe|contrato)\b",
    r"\b(calcula|calculadora|cuanto es|fecha|hora|clima|tiempo)\b",
    r"\b(busca|internet|noticias|web|correo|email|calendario)\b",
    r"\b(archivo|documento|pdf|foto|pantalla|camara)\b",
    r"\b(alarma|puerta|cerradura|luz|termostato|television)\b",
    r"\b(banco|transferencia|paga|pagar|compra|comprar|dinero)\b",
    r"\b(borra|elimina|envia|instala|ejecuta|publica|reserva)\b",
    r"\b(clave|contrasena|privad[oa]s?|secreto|dni|tarjeta)\b",
    r"\b(recuerda|recuerdame|apunta|guarda esto)\b",
    r"\b(primero|despues|luego)\b|\by a continuacion\b",
)))
CONTINUACIONES = {
    "adelante",
    "continua",
    "dale",
    "hazlo",
    "por que",
    "sigue",
    "si",
    "vale",
}


def normalizar(texto: str) -> str:
    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto.casefold())
        if unicodedata.category(caracter) != "Mn"
    )
    return " ".join(sin_acentos.split())


def usar_modelo_rapido(
    texto: str,
    max_caracteres: int,
    herramientas_anteriores: tuple[str, ...] = (),
    pregunta_anterior: str = "",
) -> bool:
    """Devuelve True solo para conversación breve sin señales de riesgo."""
    if herramientas_anteriores:
        return False
    normalizado = normalizar(texto)
    if not normalizado or len(normalizado) > max_caracteres:
        return False
    if sum(normalizado.count(signo) for signo in "?!") > 1:
        return False
    if any(patron.search(normalizado) for patron in PATRONES_ASTRA):
        return False
    limpio = normalizado.strip("¿?¡!.,;: ")
    if limpio in CONTINUACIONES and pregunta_anterior:
        return usar_modelo_rapido(
            pregunta_anterior,
            max_caracteres,
        )
    return True
