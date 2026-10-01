"""Compara el tiempo al primer texto de modelos candidatos para voz."""

from argparse import ArgumentParser
from statistics import median
from time import perf_counter

from core.chat import (
    cargar_configuracion,
    cargar_personalidad,
    crear_cliente,
)
from core.expresion import INSTRUCCIONES_VOZ, ParserExpresionVoz
from tools.registro import RegistroHerramientas


CANDIDATOS = (
    ("gpt-6-astra", "low", "default"),
    ("gpt-6-luna", "none", "default"),
)
REPETICIONES = 3
PREGUNTA = "Saluda a Jhony en una sola frase breve y natural."


def medir_modelo(
    cliente,
    modelo: str,
    esfuerzo: str,
    nivel_servicio: str,
    instrucciones: str,
    herramientas: list[dict],
) -> tuple[float, float, float, str]:
    inicio = perf_counter()
    primer_delta: list[float] = []
    primer_texto: list[float] = []
    nivel_confirmado = "desconocido"

    def publicar(fragmento: str) -> None:
        if fragmento and not primer_texto:
            primer_texto.append(perf_counter() - inicio)

    parser = ParserExpresionVoz(publicar)
    eventos = cliente.responses.create(
        model=modelo,
        instructions=instrucciones,
        input=[{"role": "user", "content": PREGUNTA}],
        max_output_tokens=600,
        service_tier=nivel_servicio,
        reasoning={"effort": esfuerzo},
        tools=herramientas,
        parallel_tool_calls=False,
        stream=True,
    )
    try:
        for evento in eventos:
            if evento.type == "response.output_text.delta":
                if not primer_delta:
                    primer_delta.append(perf_counter() - inicio)
                parser.agregar(evento.delta)
            elif evento.type == "response.completed":
                nivel_confirmado = str(
                    getattr(evento.response, "service_tier", "desconocido")
                )
        parser.finalizar()
    finally:
        eventos.close()

    if not primer_delta or not primer_texto:
        raise RuntimeError(f"{modelo} no produjo texto medible")
    return (
        primer_delta[0],
        primer_texto[0],
        perf_counter() - inicio,
        nivel_confirmado,
    )


def main() -> int:
    argumentos = ArgumentParser()
    argumentos.add_argument(
        "--modelo-fast",
        choices=["gpt-6-astra", "gpt-6-luna"],
    )
    opciones = argumentos.parse_args()
    configuracion = cargar_configuracion()
    cliente = crear_cliente(configuracion)
    instrucciones = (
        cargar_personalidad()
        + "\n\n"
        + INSTRUCCIONES_VOZ
    )
    herramientas = RegistroHerramientas.descubrir().definiciones_api()

    candidatos = (
        ((
            opciones.modelo_fast,
            "low" if opciones.modelo_fast == "gpt-6-astra" else "none",
            "fast",
        ),)
        if opciones.modelo_fast
        else CANDIDATOS
    )
    for modelo, esfuerzo, nivel_servicio in candidatos:
        muestras = [
            medir_modelo(
                cliente,
                modelo,
                esfuerzo,
                nivel_servicio,
                instrucciones,
                herramientas,
            )
            for _ in range(REPETICIONES)
        ]
        print(f"{modelo} / {esfuerzo} / {nivel_servicio}")
        print(
            "  primer delta: "
            f"{median(item[0] for item in muestras):.3f} s"
        )
        print(
            "  primer texto visible: "
            f"{median(item[1] for item in muestras):.3f} s"
        )
        print(
            "  respuesta completa: "
            f"{median(item[2] for item in muestras):.3f} s"
        )
        print(f"  nivel confirmado: {muestras[-1][3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
