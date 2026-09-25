import ast
from decimal import Decimal, localcontext
from fractions import Fraction

NOMBRE_HERRAMIENTA = "calcular"

DEFINICION_HERRAMIENTA = {
    "type": "function",
    "name": NOMBRE_HERRAMIENTA,
    "description": (
        "Calcula con exactitud una expresión aritmética. Úsala siempre "
        "que Jhony pida un cálculo, aunque parezca sencillo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "expresion": {
                "type": "string",
                "description": (
                    "Expresión con números, paréntesis y operadores "
                    "+, -, *, /, //, %, **."
                ),
            }
        },
        "required": ["expresion"],
        "additionalProperties": False,
    },
    "strict": True,
}

LONGITUD_MAXIMA = 200
EXPONENTE_MAXIMO = 100
BITS_MAXIMOS = 4096


class ErrorCalculo(ValueError):
    pass


def comprobar_tamano(valor: Fraction) -> Fraction:
    if (
        valor.numerator.bit_length() > BITS_MAXIMOS
        or valor.denominator.bit_length() > BITS_MAXIMOS
    ):
        raise ErrorCalculo("El resultado es demasiado grande")
    return valor


def convertir_numero(valor: object) -> Fraction:
    if type(valor) is int:
        return comprobar_tamano(Fraction(valor))
    if type(valor) is float:
        return comprobar_tamano(Fraction(Decimal(str(valor))))
    raise ErrorCalculo("Solo se permiten números")


def evaluar_nodo(nodo: ast.AST) -> Fraction:
    if isinstance(nodo, ast.Expression):
        return evaluar_nodo(nodo.body)

    if isinstance(nodo, ast.Constant):
        return convertir_numero(nodo.value)

    if isinstance(nodo, ast.UnaryOp):
        valor = evaluar_nodo(nodo.operand)
        if isinstance(nodo.op, ast.UAdd):
            return valor
        if isinstance(nodo.op, ast.USub):
            return -valor
        raise ErrorCalculo("Operador no permitido")

    if not isinstance(nodo, ast.BinOp):
        raise ErrorCalculo("La expresión contiene elementos no permitidos")

    izquierda = evaluar_nodo(nodo.left)
    derecha = evaluar_nodo(nodo.right)

    if isinstance(nodo.op, ast.Add):
        resultado = izquierda + derecha
    elif isinstance(nodo.op, ast.Sub):
        resultado = izquierda - derecha
    elif isinstance(nodo.op, ast.Mult):
        resultado = izquierda * derecha
    elif isinstance(nodo.op, ast.Div):
        if derecha == 0:
            raise ErrorCalculo("No se puede dividir entre cero")
        resultado = izquierda / derecha
    elif isinstance(nodo.op, ast.FloorDiv):
        if derecha == 0:
            raise ErrorCalculo("No se puede dividir entre cero")
        resultado = Fraction(izquierda // derecha)
    elif isinstance(nodo.op, ast.Mod):
        if derecha == 0:
            raise ErrorCalculo("No se puede dividir entre cero")
        resultado = izquierda % derecha
    elif isinstance(nodo.op, ast.Pow):
        if derecha.denominator != 1:
            raise ErrorCalculo("El exponente debe ser un número entero")
        exponente = derecha.numerator
        if abs(exponente) > EXPONENTE_MAXIMO:
            raise ErrorCalculo("El exponente es demasiado grande")
        if izquierda == 0 and exponente < 0:
            raise ErrorCalculo("No se puede dividir entre cero")
        resultado = izquierda**exponente
    else:
        raise ErrorCalculo("Operador no permitido")

    return comprobar_tamano(resultado)


def representar_decimal(valor: Fraction) -> str:
    with localcontext() as contexto:
        contexto.prec = 50
        decimal = Decimal(valor.numerator) / Decimal(valor.denominator)
    texto = format(decimal, "f")
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


def calcular(expresion: str) -> dict[str, str]:
    expresion = expresion.strip()
    if not expresion:
        raise ErrorCalculo("La expresión está vacía")
    if len(expresion) > LONGITUD_MAXIMA:
        raise ErrorCalculo("La expresión es demasiado larga")

    try:
        arbol = ast.parse(expresion, mode="eval")
    except SyntaxError as error:
        raise ErrorCalculo("La expresión no es válida") from error

    resultado = evaluar_nodo(arbol)
    exacto = (
        str(resultado.numerator)
        if resultado.denominator == 1
        else f"{resultado.numerator}/{resultado.denominator}"
    )
    return {
        "expresion": expresion,
        "resultado_exacto": exacto,
        "resultado_decimal": representar_decimal(resultado),
    }
