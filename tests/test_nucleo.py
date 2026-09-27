from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest
from openai import APIConnectionError

import core.chat as chat
import core.sesion as sesion
from core.errores import ErrorLimiteHerramientas, ErrorRespuestaASTRO
from core.uso import Tarifas, calcular_coste_estimado
from tools.registro import RegistroHerramientas


def crear_uso():
    return SimpleNamespace(
        input_tokens=10,
        input_tokens_details=SimpleNamespace(
            cached_tokens=0,
            cache_write_tokens=None,
        ),
        output_tokens=5,
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        total_tokens=15,
    )


def respuesta_con_llamada(
    nombre: str,
    argumentos: dict,
    numero: int,
):
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name=nombre,
                arguments=json.dumps(argumentos),
                call_id=f"call_{numero}",
            )
        ],
        usage=crear_uso(),
        model="modelo-prueba",
        service_tier="default",
    )


def respuesta_final():
    return SimpleNamespace(
        output=[SimpleNamespace(type="message")],
        usage=crear_uso(),
        model="modelo-prueba",
        service_tier="default",
    )


class APIFalsa:
    def __init__(self, respuestas: list) -> None:
        self.respuestas = list(respuestas)
        self.llamadas: list[dict] = []

    def create(self, **opciones):
        self.llamadas.append(deepcopy(opciones))
        respuesta = self.respuestas.pop(0)
        eventos = []
        if not any(
            elemento.type == "function_call"
            for elemento in respuesta.output
        ):
            eventos.append(
                SimpleNamespace(
                    type="response.output_text.delta",
                    delta="Resultado final: 4072.",
                )
            )
        eventos.append(
            SimpleNamespace(
                type="response.completed",
                response=respuesta,
            )
        )
        return iter(eventos)


class APIMixta(APIFalsa):
    def create(self, **opciones):
        self.llamadas.append(deepcopy(opciones))
        respuesta = self.respuestas.pop(0)
        if respuesta == "fallo":
            return iter([SimpleNamespace(type="error")])
        eventos = []
        if not any(
            elemento.type == "function_call"
            for elemento in respuesta.output
        ):
            eventos.append(
                SimpleNamespace(
                    type="response.output_text.delta",
                    delta="Continuación segura.",
                )
            )
        eventos.append(
            SimpleNamespace(
                type="response.completed",
                response=respuesta,
            )
        )
        return iter(eventos)


class APIFalloParcial(APIFalsa):
    def create(self, **opciones):
        self.llamadas.append(deepcopy(opciones))
        return iter(
            [
                SimpleNamespace(
                    type="response.output_text.delta",
                    delta="Texto parcial. ",
                ),
                SimpleNamespace(type="error"),
            ]
        )


class RegistroContador:
    def __init__(self) -> None:
        self.real = RegistroHerramientas.descubrir()
        self.ejecuciones = 0

    def definiciones_api(self):
        return self.real.definiciones_api()

    def ejecutar(self, nombre, argumentos, contexto):
        self.ejecuciones += 1
        return self.real.ejecutar(nombre, argumentos, contexto)


def test_calcular_coste_estimado() -> None:
    tarifas = Tarifas(
        entrada_usd_millon=10,
        entrada_cache_usd_millon=1,
        escritura_cache_usd_millon=12.5,
        salida_usd_millon=50,
    )

    coste = calcular_coste_estimado(
        tokens_entrada=1000,
        tokens_entrada_cache=200,
        tokens_escritura_cache=100,
        tokens_salida=50,
        tarifas=tarifas,
    )

    assert coste == pytest.approx(0.01095)


def test_explicar_limite_herramientas() -> None:
    mensaje = chat.explicar_error(ErrorLimiteHerramientas())

    assert "evitar un bucle" in mensaje
    assert "gasto inesperado" in mensaje


def test_error_de_conexion_nombra_el_proveedor_activo() -> None:
    error = APIConnectionError(
        request=SimpleNamespace(
            method="POST",
            url="https://openrouter.ai/api/v1/responses",
        )
    )

    mensaje = chat.explicar_error(error, "OpenRouter")

    assert "conectar con OpenRouter" in mensaje


def test_bucle_agente_encadena_tres_herramientas(
    monkeypatch,
    capsys,
) -> None:
    api = APIFalsa(
        [
            respuesta_con_llamada("obtener_fecha_hora", {}, 1),
            respuesta_con_llamada(
                "calcular",
                {"expresion": "2026 + 10"},
                2,
            ),
            respuesta_con_llamada(
                "calcular",
                {"expresion": "2036 * 2"},
                3,
            ),
            respuesta_final(),
        ]
    )
    monkeypatch.setattr(chat, "guardar_registro", lambda registro: None)

    resultado = chat.responder(
        SimpleNamespace(responses=api),
        [{"role": "user", "content": "Tarea de tres pasos"}],
        "Personalidad de prueba",
        chat.cargar_configuracion(),
        RegistroHerramientas.descubrir(),
    )

    capsys.readouterr()
    assert resultado.texto == "Resultado final: 4072."
    assert len(resultado.registros) == 4
    assert resultado.herramientas_usadas == (
        "obtener_fecha_hora",
        "calcular",
        "calcular",
    )
    assert all(
        registro.proveedor == "openai"
        for registro in resultado.registros
    )
    assert all(
        registro.tokens_escritura_cache == 0
        for registro in resultado.registros
    )
    assert len(api.llamadas) == 4
    assert "registros fiables generados por el núcleo" in (
        api.llamadas[-1]["instructions"]
    )
    salida_final = json.loads(
        api.llamadas[-1]["input"][-1]["output"]
    )
    assert salida_final["resultado_exacto"] == "4072"


def test_sesion_conserva_herramientas_en_contexto_interno(
    monkeypatch,
) -> None:
    resultado = chat.ResultadoRespuesta(
        texto="El resultado es 42.",
        registros=(),
        herramientas_usadas=("calcular",),
    )
    monkeypatch.setattr(
        sesion,
        "responder_con_rutas",
        lambda *args: resultado,
    )
    nucleo = SimpleNamespace(
        rutas_para_turno=lambda: (
            chat.RutaIA(
                SimpleNamespace(),
                chat.cargar_configuracion(),
            ),
        ),
        personalidad="Personalidad de prueba",
        registro=RegistroHerramientas.descubrir(),
        registrar_fallo=lambda proveedor, error: None,
        registrar_exito=lambda proveedor: None,
    )
    instancia = sesion.SesionASTRO(
        nucleo=nucleo,
    )

    respuesta = instancia.preguntar("Calcula 40 + 2")

    assert respuesta is resultado
    assert instancia.historial[0] == {
        "role": "user",
        "content": "Calcula 40 + 2",
    }
    assert instancia.historial[1]["content"].startswith(
        "El resultado es 42."
    )
    assert "herramientas usadas en este turno: calcular" in (
        instancia.historial[1]["content"]
    )


def test_editar_turno_rebobina_y_sustituye_historial(monkeypatch) -> None:
    respuestas = iter(("Primera", "Segunda", "Corregida"))

    def responder(*args):
        return chat.ResultadoRespuesta(
            texto=next(respuestas),
            registros=(),
            herramientas_usadas=(),
        )

    monkeypatch.setattr(sesion, "responder_con_rutas", responder)
    nucleo = SimpleNamespace(
        rutas_para_turno=lambda: (
            chat.RutaIA(SimpleNamespace(), chat.cargar_configuracion()),
        ),
        personalidad="Personalidad de prueba",
        registro=RegistroHerramientas.descubrir(),
        registrar_fallo=lambda proveedor, error: None,
        registrar_exito=lambda proveedor: None,
    )
    instancia = sesion.SesionASTRO(nucleo=nucleo)
    instancia.preguntar("Mensaje uno")
    instancia.preguntar("Mensaje dos")

    resultado = instancia.editar_turno(0, "Mensaje corregido")

    assert resultado.texto == "Corregida"
    assert instancia.cantidad_turnos == 1
    assert instancia.historial == [
        {"role": "user", "content": "Mensaje corregido"},
        {"role": "assistant", "content": "Corregida"},
    ]


def test_editar_turno_fallido_restaura_historial(monkeypatch) -> None:
    historial = [
        {"role": "user", "content": "Original"},
        {"role": "assistant", "content": "Respuesta original"},
    ]
    instancia = sesion.SesionASTRO(
        nucleo=SimpleNamespace(
            rutas_para_turno=lambda: (),
            personalidad="Personalidad de prueba",
            registro=RegistroHerramientas.descubrir(),
            registrar_fallo=lambda proveedor, error: None,
            registrar_exito=lambda proveedor: None,
        ),
        historial=list(historial),
    )
    monkeypatch.setattr(
        sesion,
        "responder_con_rutas",
        lambda *args: (_ for _ in ()).throw(ErrorRespuestaASTRO()),
    )
    monkeypatch.setattr(sesion, "guardar_registro_error", lambda registro: None)

    with pytest.raises(ErrorRespuestaASTRO):
        instancia.editar_turno(0, "Corrección fallida")

    assert instancia.historial == historial


def test_editar_turno_inexistente_no_cambia_historial() -> None:
    historial = [
        {"role": "user", "content": "Original"},
        {"role": "assistant", "content": "Respuesta original"},
    ]
    instancia = sesion.SesionASTRO(
        nucleo=SimpleNamespace(),
        historial=list(historial),
    )

    with pytest.raises(ValueError, match="no existe"):
        instancia.editar_turno(2, "Imposible")

    assert instancia.historial == historial


def crear_nucleo_con_rutas(
    rutas: tuple[str, ...],
) -> tuple[sesion.NucleoASTRO, list[tuple[str, str]]]:
    configuracion = chat.cargar_configuracion()
    fallos: list[tuple[str, str]] = []
    ajustes = SimpleNamespace(
        rutas_para_turno=lambda: rutas,
        obtener=lambda: SimpleNamespace(
            modelos=dict(configuracion.modelos_por_proveedor)
        ),
        registrar_fallo=lambda proveedor, mensaje: fallos.append(
            (proveedor, mensaje)
        ),
    )
    nucleo = sesion.NucleoASTRO(
        configuracion=configuracion,
        personalidad="Personalidad de prueba",
        registro=RegistroHerramientas.descubrir(),
        ajustes_ia=ajustes,
    )
    return nucleo, fallos


def test_respaldo_sin_clave_no_bloquea_principal(monkeypatch) -> None:
    nucleo, fallos = crear_nucleo_con_rutas(("openai", "openrouter"))
    cliente_principal = SimpleNamespace()

    def crear(configuracion):
        if configuracion.proveedor.identificador == "openrouter":
            raise RuntimeError("Falta la clave del respaldo")
        return cliente_principal

    monkeypatch.setattr(sesion, "crear_cliente", crear)

    rutas = nucleo.rutas_para_turno()

    assert len(rutas) == 1
    assert rutas[0].cliente is cliente_principal
    assert rutas[0].configuracion.proveedor.identificador == "openai"
    assert fallos == [("openrouter", "RuntimeError")]


def test_principal_sin_clave_utiliza_respaldo(monkeypatch) -> None:
    nucleo, fallos = crear_nucleo_con_rutas(("openai", "openrouter"))
    cliente_respaldo = SimpleNamespace()

    def crear(configuracion):
        if configuracion.proveedor.identificador == "openai":
            raise RuntimeError("Falta la clave principal")
        return cliente_respaldo

    monkeypatch.setattr(sesion, "crear_cliente", crear)

    rutas = nucleo.rutas_para_turno()

    assert len(rutas) == 1
    assert rutas[0].cliente is cliente_respaldo
    assert rutas[0].configuracion.proveedor.identificador == "openrouter"
    assert fallos == [("openai", "RuntimeError")]


def test_ninguna_clave_produce_error_controlado(monkeypatch) -> None:
    nucleo, fallos = crear_nucleo_con_rutas(("openai", "openrouter"))

    def fallar(configuracion):
        raise RuntimeError(
            f"Falta la clave de {configuracion.proveedor.identificador}"
        )

    monkeypatch.setattr(sesion, "crear_cliente", fallar)

    with pytest.raises(ErrorRespuestaASTRO):
        nucleo.rutas_para_turno()

    assert fallos == [
        ("openai", "RuntimeError"),
        ("openrouter", "RuntimeError"),
    ]


def test_respaldo_continua_texto_parcial(monkeypatch) -> None:
    principal = APIFalloParcial([])
    respaldo = APIMixta([respuesta_final()])
    configuracion = chat.cargar_configuracion()
    configuracion_respaldo = replace(
        configuracion,
        proveedor=configuracion.proveedores["openrouter"],
        modelo=configuracion.modelos_por_proveedor["openrouter"],
    )
    emitido: list[str] = []
    cambios: list[chat.CambioProveedor] = []
    monkeypatch.setattr(chat, "guardar_registro", lambda registro: None)

    resultado = chat.responder_con_rutas(
        rutas=(
            chat.RutaIA(SimpleNamespace(responses=principal), configuracion),
            chat.RutaIA(
                SimpleNamespace(responses=respaldo),
                configuracion_respaldo,
            ),
        ),
        historial=[{"role": "user", "content": "Continúa"}],
        personalidad="Personalidad de prueba",
        registro=RegistroHerramientas.descubrir(),
        emitir_texto=emitido.append,
        emitir_cambio=cambios.append,
    )

    assert resultado.texto == "Texto parcial. Continuación segura."
    assert "".join(emitido) == resultado.texto
    assert resultado.proveedor_final == "openrouter"
    assert cambios[0].continuo_texto_parcial is True
    assert respaldo.llamadas[0]["input"][-2] == {
        "role": "assistant",
        "content": "Texto parcial. ",
    }


def test_respaldo_no_repite_herramienta_ejecutada(monkeypatch) -> None:
    principal = APIMixta(
        [
            respuesta_con_llamada("calcular", {"expresion": "40 + 2"}, 1),
            "fallo",
        ]
    )
    respaldo = APIMixta([respuesta_final()])
    configuracion = chat.cargar_configuracion()
    configuracion_respaldo = replace(
        configuracion,
        proveedor=configuracion.proveedores["openrouter"],
        modelo=configuracion.modelos_por_proveedor["openrouter"],
    )
    registro = RegistroContador()
    monkeypatch.setattr(chat, "guardar_registro", lambda registro: None)

    resultado = chat.responder_con_rutas(
        rutas=(
            chat.RutaIA(SimpleNamespace(responses=principal), configuracion),
            chat.RutaIA(
                SimpleNamespace(responses=respaldo),
                configuracion_respaldo,
            ),
        ),
        historial=[{"role": "user", "content": "Calcula 40 + 2"}],
        personalidad="Personalidad de prueba",
        registro=registro,
    )

    assert registro.ejecuciones == 1
    assert resultado.proveedor_final == "openrouter"
    assert any(
        isinstance(elemento, dict)
        and elemento.get("type") == "function_call_output"
        for elemento in respaldo.llamadas[0]["input"]
    )
