from collections.abc import Callable
from dataclasses import dataclass, field, replace

from openai import APIError, OpenAI

from core.ajustes_ia import AjustesIA, ServicioAjustesIA
from core.chat import (
    Configuracion,
    ResultadoRespuesta,
    RutaIA,
    cargar_configuracion,
    cargar_personalidad,
    crear_cliente,
    es_error_reintentable,
    responder_con_rutas,
)
from core.errores import (
    ErrorRespuestaASTRO,
    crear_registro_error,
    guardar_registro_error,
)
from tools.registro import RegistroHerramientas

EmitirTexto = Callable[[str], None]
EmitirCambio = Callable[[object], None]


@dataclass
class NucleoASTRO:
    configuracion: Configuracion
    personalidad: str
    registro: RegistroHerramientas
    ajustes_ia: ServicioAjustesIA
    clientes: dict[str, OpenAI] = field(default_factory=dict)

    def nueva_sesion(self) -> "SesionASTRO":
        return SesionASTRO(nucleo=self)

    def configuracion_para(self, proveedor: str) -> Configuracion:
        ajustes = self.ajustes_ia.obtener()
        return replace(
            self.configuracion,
            proveedor=self.configuracion.proveedores[proveedor],
            modelo=ajustes.modelos[proveedor],
        )

    def rutas_para_turno(self) -> tuple[RutaIA, ...]:
        rutas: list[RutaIA] = []
        ultimo_error: RuntimeError | None = None
        for proveedor in self.ajustes_ia.rutas_para_turno():
            configuracion = self.configuracion_para(proveedor)
            cliente = self.clientes.get(proveedor)
            if cliente is None:
                try:
                    cliente = crear_cliente(configuracion)
                except RuntimeError as error:
                    self.registrar_fallo(proveedor, error)
                    ultimo_error = error
                    continue
                self.clientes[proveedor] = cliente
            rutas.append(RutaIA(cliente, configuracion))
        if not rutas:
            raise ErrorRespuestaASTRO() from ultimo_error
        return tuple(rutas)

    def estado_ia(self) -> dict[str, object]:
        ajustes = self.ajustes_ia.obtener()
        estado = self.ajustes_ia.estado()
        activo = str(estado["active"])
        proveedores = [
            {
                "id": identificador,
                "name": proveedor.nombre_visible,
                "model": ajustes.modelos[identificador],
            }
            for identificador, proveedor in self.configuracion.proveedores.items()
        ]
        return {
            **estado,
            "provider": activo,
            "provider_name": self.configuracion.proveedores[
                activo
            ].nombre_visible,
            "model": ajustes.modelos[activo],
            "primary": ajustes.principal,
            "fallback": ajustes.respaldo,
            "automatic": ajustes.cambio_automatico,
            "retry_seconds": ajustes.reintento_principal_segundos,
            "providers": proveedores,
        }

    def actualizar_ajustes_ia(self, ajustes: AjustesIA) -> dict[str, object]:
        self.ajustes_ia.actualizar(ajustes)
        return self.estado_ia()

    def registrar_fallo(self, proveedor: str, error: Exception) -> None:
        self.ajustes_ia.registrar_fallo(
            proveedor,
            type(error).__name__,
        )

    def registrar_exito(self, proveedor: str) -> tuple[str, str] | None:
        return self.ajustes_ia.registrar_exito(proveedor)


@dataclass
class SesionASTRO:
    nucleo: NucleoASTRO
    historial: list[dict[str, str]] = field(default_factory=list)

    @property
    def cantidad_turnos(self) -> int:
        return len(self.historial) // 2

    def preguntar(
        self,
        pregunta: str,
        emitir_texto: EmitirTexto | None = None,
        emitir_cambio: EmitirCambio | None = None,
    ) -> ResultadoRespuesta:
        pregunta = pregunta.strip()
        if not pregunta:
            raise ValueError("La pregunta no puede estar vacía")

        self.historial.append({"role": "user", "content": pregunta})
        try:
            resultado = responder_con_rutas(
                self.nucleo.rutas_para_turno(),
                self.historial,
                self.nucleo.personalidad,
                self.nucleo.registro,
                emitir_texto,
                emitir_cambio,
                self.nucleo.registrar_fallo,
                self.nucleo.registrar_exito,
            )
        except (APIError, ErrorRespuestaASTRO) as error:
            self.historial.pop()
            guardar_registro_error(
                crear_registro_error(
                    error,
                    es_error_reintentable(error),
                )
            )
            raise

        contenido_historial = resultado.texto
        if resultado.herramientas_usadas:
            nombres = ", ".join(resultado.herramientas_usadas)
            contenido_historial += (
                "\n\n[Contexto interno de ASTRO: herramientas usadas "
                f"en este turno: {nombres}.]"
            )
        self.historial.append(
            {"role": "assistant", "content": contenido_historial}
        )
        return resultado

    def editar_turno(
        self,
        indice: int,
        pregunta: str,
        emitir_texto: EmitirTexto | None = None,
        emitir_cambio: EmitirCambio | None = None,
    ) -> ResultadoRespuesta:
        if type(indice) is not int or not 0 <= indice < self.cantidad_turnos:
            raise ValueError("El turno que intentas editar no existe")

        historial_original = self.historial
        self.historial = self.historial[: indice * 2]
        try:
            return self.preguntar(
                pregunta,
                emitir_texto,
                emitir_cambio,
            )
        except Exception:
            self.historial = historial_original
            raise


def crear_nucleo() -> NucleoASTRO:
    configuracion = cargar_configuracion()
    ajustes = AjustesIA(
        principal=configuracion.proveedor.identificador,
        respaldo=configuracion.proveedor_respaldo,
        modelos=dict(configuracion.modelos_por_proveedor),
        cambio_automatico=configuracion.cambio_automatico,
        reintento_principal_segundos=(
            configuracion.reintento_principal_segundos
        ),
    )
    return NucleoASTRO(
        configuracion=configuracion,
        personalidad=cargar_personalidad(),
        registro=RegistroHerramientas.descubrir(),
        ajustes_ia=ServicioAjustesIA(
            proveedores=set(configuracion.proveedores),
            ajustes_predeterminados=ajustes,
        ),
    )
