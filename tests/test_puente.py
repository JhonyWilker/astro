import asyncio
import json
from http import HTTPStatus

import pytest
import websockets.asyncio.client as ws_client
from websockets.exceptions import ConnectionClosed, InvalidStatus

from voice.estados import EstadoVoz, IndicadorEstados
from voice.puente import PuenteLocal, origen_configurado


@pytest.fixture
def puente(tmp_path):
    servidor = PuenteLocal(ruta_info=tmp_path / "puente.json")
    assert servidor.iniciar() is True
    yield servidor
    servidor.detener()


async def conectar(servidor, **opciones):
    return await ws_client.connect(f"ws://127.0.0.1:{servidor.puerto}", **opciones)


async def conectar_autenticado(servidor):
    conexion = await conectar(servidor)
    await conexion.send(json.dumps({"type": "auth", "token": servidor.token}))
    return conexion


async def recibir(conexion):
    return json.loads(await asyncio.wait_for(conexion.recv(), 3))


def test_cliente_autenticado_recibe_hello_y_estados_en_orden(puente) -> None:
    async def prueba():
        conexion = await conectar_autenticado(puente)
        assert (await recibir(conexion))["type"] == "hello"
        puente.publicar_estado(EstadoVoz.ESCUCHANDO, "Habla ahora")
        puente.publicar("transcript", text="enciende la luz")
        puente.publicar_estado(EstadoVoz.PENSANDO, "Preparando respuesta")
        primero = await recibir(conexion)
        segundo = await recibir(conexion)
        tercero = await recibir(conexion)
        assert (primero["type"], primero["state"]) == ("state", "escuchando")
        assert segundo["type"] == "transcript" and segundo["text"] == "enciende la luz"
        assert (tercero["type"], tercero["state"]) == ("state", "pensando")
        assert primero["v"] == 1 and "ts" in primero
        await conexion.close()

    asyncio.run(prueba())


def test_token_incorrecto_se_rechaza_sin_enviar_nada(puente) -> None:
    async def prueba():
        conexion = await conectar(puente)
        await conexion.send(json.dumps({"type": "auth", "token": "falso"}))
        with pytest.raises(ConnectionClosed) as error:
            await asyncio.wait_for(conexion.recv(), 3)
        assert error.value.rcvd.code == 1008

    asyncio.run(prueba())


def test_mensaje_que_no_es_auth_se_rechaza(puente) -> None:
    async def prueba():
        conexion = await conectar(puente)
        await conexion.send("esto no es json")
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(conexion.recv(), 3)

    asyncio.run(prueba())


def test_json_valido_que_no_es_objeto_se_rechaza(puente) -> None:
    async def prueba():
        conexion = await conectar(puente)
        await conexion.send("[]")
        with pytest.raises(ConnectionClosed):
            await asyncio.wait_for(conexion.recv(), 3)

    asyncio.run(prueba())


def test_origen_ajeno_se_rechaza_con_403(puente) -> None:
    async def prueba():
        with pytest.raises(InvalidStatus) as error:
            await conectar(puente, origin="https://sitio-malicioso.example")
        assert error.value.response.status_code == 403

    asyncio.run(prueba())


def test_origen_de_astro_se_acepta(puente) -> None:
    async def prueba():
        conexion = await conectar(puente, origin="https://astro-vps.tailbee6db.ts.net")
        await conexion.send(json.dumps({"type": "auth", "token": puente.token}))
        assert (await recibir(conexion))["type"] == "hello"
        await conexion.close()

    asyncio.run(prueba())


def test_origen_se_deriva_de_la_url_configurada(monkeypatch) -> None:
    monkeypatch.setenv("ASTRO_URL_BASE", "https://otro-astro.example/ruta")
    assert origen_configurado() == "https://otro-astro.example"


def test_host_ajeno_se_rechaza() -> None:
    class Peticion:
        def __init__(self, cabeceras):
            self.headers = cabeceras

    class Conexion:
        def respond(self, estado, texto):
            return estado

    servidor = PuenteLocal()
    rechazo = servidor._comprobar_origen(Conexion(), Peticion({"Host": "evil.example:80"}))
    assert rechazo == HTTPStatus.FORBIDDEN
    assert servidor._comprobar_origen(Conexion(), Peticion({"Host": "127.0.0.1:5000"})) is None
    assert servidor._comprobar_origen(Conexion(), Peticion({"Host": "localhost:5000"})) is None


def test_sin_autenticar_a_tiempo_se_cierra(tmp_path) -> None:
    servidor = PuenteLocal(ruta_info=tmp_path / "p.json", espera_autenticacion=0.3)
    assert servidor.iniciar()
    try:
        async def prueba():
            conexion = await conectar(servidor)
            with pytest.raises(ConnectionClosed):
                await asyncio.wait_for(conexion.recv(), 3)

        asyncio.run(prueba())
    finally:
        servidor.detener()


def test_limite_de_clientes(tmp_path) -> None:
    servidor = PuenteLocal(ruta_info=tmp_path / "p.json", maximo_clientes=1)
    assert servidor.iniciar()
    try:
        async def prueba():
            primero = await conectar_autenticado(servidor)
            assert (await recibir(primero))["type"] == "hello"
            segundo = await conectar(servidor)
            with pytest.raises(ConnectionClosed):
                # el servidor puede cerrar antes de leer la autenticación
                await segundo.send(json.dumps({"type": "auth", "token": servidor.token}))
                await asyncio.wait_for(segundo.recv(), 3)
            await primero.close()

        asyncio.run(prueba())
    finally:
        servidor.detener()


def test_cliente_nuevo_recibe_el_estado_actual(puente) -> None:
    puente.publicar_estado(EstadoVoz.PENSANDO, "Preparando respuesta")

    async def prueba():
        await asyncio.sleep(0.2)
        conexion = await conectar_autenticado(puente)
        hola = await recibir(conexion)
        assert hola["type"] == "hello"
        assert hola["state"] == "pensando"
        assert hola["detail"] == "Preparando respuesta"
        await conexion.close()

    asyncio.run(prueba())


def test_cliente_nuevo_recibe_el_ultimo_nivel_del_microfono(puente) -> None:
    puente.publicar_nivel(0.73)

    async def prueba():
        conexion = await conectar_autenticado(puente)
        hola = await recibir(conexion)
        assert hola["type"] == "hello"
        assert hola["mic_level"] == 0.73
        await conexion.close()

    asyncio.run(prueba())


def test_nivel_del_microfono_se_limita_y_no_satura_el_puente(monkeypatch) -> None:
    servidor = PuenteLocal()
    enviados = []
    tiempos = iter((1.0, 1.05, 1.11))
    monkeypatch.setattr("voice.puente.time.monotonic", lambda: next(tiempos))
    monkeypatch.setattr(
        servidor,
        "publicar",
        lambda tipo, **datos: enviados.append((tipo, datos)),
    )

    servidor.publicar_nivel(-2)
    servidor.publicar_nivel(0.4)
    servidor.publicar_nivel(3)

    assert enviados == [
        ("mic_level", {"level": 0.0}),
        ("mic_level", {"level": 1.0}),
    ]
    assert servidor._ultimo_nivel == 1.0



def test_un_cliente_que_desaparece_no_afecta_a_otro(puente) -> None:
    async def prueba():
        caido = await conectar_autenticado(puente)
        vivo = await conectar_autenticado(puente)
        await recibir(caido)
        await recibir(vivo)
        caido.transport.abort()
        for texto in ("uno", "dos", "tres"):
            puente.publicar("transcript", text=texto)
        recibidos = [(await recibir(vivo))["text"] for _ in range(3)]
        assert recibidos == ["uno", "dos", "tres"]
        await vivo.close()

    asyncio.run(prueba())


def test_publicar_sin_nadie_escuchando_no_falla(puente) -> None:
    for _ in range(50):
        puente.publicar_estado(EstadoVoz.ESCUCHANDO, "x")
        puente.publicar("transcript", text="nadie escucha")


def test_publicar_antes_de_iniciar_y_tras_detener_no_falla(tmp_path) -> None:
    servidor = PuenteLocal(ruta_info=tmp_path / "p.json")
    servidor.publicar("state", state="dormido")  # aún no iniciado
    assert servidor.iniciar()
    servidor.detener()
    servidor.publicar("state", state="dormido")  # ya detenido
    servidor.detener()  # detener dos veces tampoco falla


def test_archivo_con_puerto_y_token_se_crea_y_se_borra(tmp_path) -> None:
    ruta = tmp_path / "puente.json"
    servidor = PuenteLocal(ruta_info=ruta)
    assert servidor.iniciar()
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["port"] == servidor.puerto
    assert datos["token"] == servidor.token
    assert len(servidor.token) >= 32
    servidor.detener()
    assert not ruta.exists()


def test_cada_arranque_genera_un_token_nuevo(tmp_path) -> None:
    uno = PuenteLocal(ruta_info=tmp_path / "a.json")
    otro = PuenteLocal(ruta_info=tmp_path / "b.json")
    assert uno.token != otro.token


def test_la_herramienta_en_uso_llega_al_receptor_por_el_puente(puente) -> None:
    indicador = IndicadorEstados(
        sonidos=False,
        salida=lambda _: None,
        al_cambiar=puente.publicar_estado,
    )

    async def prueba():
        conexion = await conectar_autenticado(puente)
        assert (await recibir(conexion))["type"] == "hello"
        indicador.cambiar(EstadoVoz.DORMIDO)
        indicador.cambiar(EstadoVoz.ESCUCHANDO, "Habla ahora")
        indicador.cambiar(EstadoVoz.PENSANDO, "Transcribiendo")
        indicador.cambiar(EstadoVoz.EJECUTANDO, "calcular")
        indicador.cambiar(EstadoVoz.PENSANDO, sonido=False)
        indicador.cambiar(EstadoVoz.HABLANDO, "Respondiendo")
        estados = []
        for _ in range(6):
            evento = await recibir(conexion)
            estados.append((evento["state"], evento["detail"]))
        assert estados[3] == ("ejecutando", "calcular")
        assert [nombre for nombre, _ in estados] == [
            "dormido", "escuchando", "pensando", "ejecutando", "pensando", "hablando",
        ]
        await conexion.close()

    asyncio.run(prueba())
