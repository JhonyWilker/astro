"""Aplicación de escritorio de ASTRO: PWA y supervisor local de voz.

Uso: python -m gui.app
"""
import sys
from pathlib import Path

from PySide6.QtCore import QDateTime, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from gui import vinculacion
from gui.atajo import AtajoSilencio
from gui.indicador import APARIENCIAS, IndicadorFlotante, apariencia_para, crear_icono
from gui.instancia import BloqueoInstancia
from gui.receptor import ReceptorPuente
from gui.supervisor import lanzar_independiente
from gui.vinculacion import ErrorVinculacion

CARPETA_PERFIL = Path(__file__).resolve().parents[1] / "data" / "gui"
RUTA_BLOQUEO_APP = CARPETA_PERFIL / "app.lock"
INTERVALO_COMPROBACION_MS = 60_000
INTERVALO_RENOVACION_COOKIE_MS = 86_400_000


class Hilo(QThread):
    """Ejecuta una llamada de red fuera del hilo de la interfaz."""

    resultado = Signal(object)

    def __init__(self, funcion, *argumentos):
        super().__init__()
        self.funcion = funcion
        self.argumentos = argumentos

    def run(self):
        try:
            self.resultado.emit(("ok", self.funcion(*self.argumentos)))
        except Exception as error:  # se devuelve al hilo de la interfaz
            self.resultado.emit(("error", error))


class DialogoVinculacion(QDialog):
    def __init__(self):
        super().__init__()
        self.token = None
        self.hilo = None
        self.setWindowTitle("Vincular este PC con ASTRO")
        self.setMinimumWidth(380)
        explicacion = QLabel(
            "En ASTRO del iPhone: Estado → Añadir dispositivo (rol personal).\n"
            "Escribe aquí el código de 8 cifras."
        )
        self.campo = QLineEdit()
        self.campo.setPlaceholderText("Código de 8 cifras")
        self.campo.setMaxLength(12)
        self.campo.returnPressed.connect(self.vincular)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #ef4444")
        self.error.setWordWrap(True)
        self.boton = QPushButton("Vincular")
        self.boton.setDefault(True)
        self.boton.clicked.connect(self.vincular)
        salir = QPushButton("Salir")
        salir.clicked.connect(self.reject)
        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(salir)
        botones.addWidget(self.boton)
        diseno = QVBoxLayout(self)
        for elemento in (explicacion, self.campo, self.error):
            diseno.addWidget(elemento)
        diseno.addLayout(botones)

    def vincular(self):
        codigo = self.campo.text().strip()
        if not codigo:
            return
        self.boton.setEnabled(False)
        self.error.setText("Comprobando…")
        self.hilo = Hilo(vinculacion.canjear_codigo, codigo)
        self.hilo.resultado.connect(self.al_canjear)
        self.hilo.start()

    def al_canjear(self, salida):
        tipo, valor = salida
        self.boton.setEnabled(True)
        if tipo == "ok":
            vinculacion.guardar_token(valor)
            self.token = valor
            self.accept()
        elif isinstance(valor, ErrorVinculacion):
            self.error.setText(str(valor))
        else:
            self.error.setText("Error inesperado al vincular.")


class Vista(QWebEngineView):
    """Ventana PWA; cerrarla la oculta y ASTRO continúa en la bandeja."""

    silencio_solicitado = Signal()

    def __init__(self):
        super().__init__()
        self.boton_microfono = QPushButton("🎙 Micrófono activo", self)
        self.boton_microfono.setToolTip("Alternar micrófono · Ctrl+Alt+S")
        self.boton_microfono.setStyleSheet(
            "QPushButton { background:#0f172a; color:#e2e8f0; "
            "border:1px solid #38bdf8; border-radius:16px; padding:6px 12px; }"
            "QPushButton:disabled { color:#64748b; border-color:#475569; }"
        )
        self.boton_microfono.clicked.connect(self.silencio_solicitado.emit)
        self.boton_microfono.setEnabled(False)

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        ancho = 174
        self.boton_microfono.setGeometry(self.width() - ancho - 12, 12, ancho, 34)
        self.boton_microfono.raise_()

    def actualizar_microfono(self, silenciado, habilitado):
        self.boton_microfono.setText(
            "🔇 Micrófono apagado" if silenciado else "🎙 Micrófono activo"
        )
        self.boton_microfono.setEnabled(habilitado)

    def closeEvent(self, evento):
        evento.ignore()
        self.hide()


class Aplicacion:
    def __init__(self):
        perfil = QWebEngineProfile("astro-gui")
        perfil.setPersistentStoragePath(str(CARPETA_PERFIL))
        perfil.setCachePath(str(CARPETA_PERFIL / "cache"))
        perfil.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self.perfil = perfil
        self.vista = Vista()
        self.vista.silencio_solicitado.connect(self.alternar_microfono)
        self.vista.setPage(QWebEnginePage(perfil, self.vista))
        self.vista.setWindowTitle("ASTRO")
        self.vista.resize(420, 800)
        self.estado_actual = "desconectado"
        self.detalle_actual = APARIENCIAS["desconectado"].texto
        self.nivel_microfono = 0.0
        self.voz_conectada = False
        self.solicitud_microfono_pendiente = False
        self.indicador = IndicadorFlotante()
        self.indicador.activado.connect(self.mostrar_ventana)
        self.receptor = ReceptorPuente()
        self.receptor.evento.connect(self.al_evento_voz)
        self.receptor.conexion.connect(self.al_conexion_voz)
        self.atajo = AtajoSilencio()
        self.atajo.activado.connect(self.alternar_microfono)
        self.bandeja = QSystemTrayIcon()
        self.menu_bandeja = QMenu()
        self.accion_estado = QAction(self.detalle_actual)
        self.accion_estado.setEnabled(False)
        self.accion_mostrar = QAction("Abrir ASTRO")
        self.accion_mostrar.triggered.connect(self.mostrar_ventana)
        self.accion_microfono = QAction("Silenciar micrófono")
        self.accion_microfono.setCheckable(True)
        self.accion_microfono.setEnabled(False)
        self.accion_microfono.triggered.connect(self.alternar_microfono)
        self.accion_salir = QAction("Salir de la interfaz")
        self.accion_salir.triggered.connect(self.salir_gui)
        self.menu_bandeja.addAction(self.accion_estado)
        self.menu_bandeja.addSeparator()
        self.menu_bandeja.addAction(self.accion_microfono)
        self.menu_bandeja.addAction(self.accion_mostrar)
        self.menu_bandeja.addAction(self.accion_salir)
        self.bandeja.setContextMenu(self.menu_bandeja)
        self.bandeja.activated.connect(self.al_activar_bandeja)
        self.hilo = None
        self.temporizador = QTimer()
        self.temporizador.setInterval(INTERVALO_COMPROBACION_MS)
        self.temporizador.timeout.connect(self.comprobar)
        self.temporizador_cookie = QTimer()
        self.temporizador_cookie.setInterval(INTERVALO_RENOVACION_COOKIE_MS)
        self.temporizador_cookie.timeout.connect(self.renovar_cookie)

    def iniciar(self):
        self.actualizar_visual()
        self.bandeja.show()
        self.indicador.mostrar_en_esquina()
        self.receptor.iniciar()
        if not self.atajo.iniciar():
            print("[AVISO] No se pudo registrar el atajo global Ctrl+Alt+S.")
        token = vinculacion.leer_token()
        if token is None:
            self.vincular()
            return
        self.lanzar_comprobacion(token, self.al_arrancar)

    def lanzar_comprobacion(self, token, destino):
        if self.hilo is not None and self.hilo.isRunning():
            return
        self.hilo = Hilo(vinculacion.comprobar_token, token)
        self.hilo.resultado.connect(lambda salida: destino(token, salida))
        self.hilo.start()

    def al_arrancar(self, token, salida):
        vigente = salida[1] if salida[0] == "ok" else None
        if vigente is False:
            self.revocado()
        else:
            self.mostrar(token)  # None = sin conexión: se abre igualmente

    def comprobar(self):
        token = vinculacion.leer_token()
        if token is not None:
            self.lanzar_comprobacion(token, self.al_comprobar)

    def al_comprobar(self, token, salida):
        if salida[0] == "ok" and salida[1] is False:
            self.revocado()

    def mostrar(self, token):
        self.inyectar_cookie(token)
        self.vista.load(QUrl(vinculacion.url_base_configurada()))
        self.vista.show()
        self.temporizador.start()
        self.temporizador_cookie.start()

    def mostrar_ventana(self):
        self.vista.showNormal()
        self.vista.raise_()
        self.vista.activateWindow()

    def al_activar_bandeja(self, razon):
        if razon in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.mostrar_ventana()

    def al_conexion_voz(self, conectada):
        self.voz_conectada = conectada
        if not conectada:
            self.estado_actual = "desconectado"
            self.detalle_actual = APARIENCIAS["desconectado"].texto
            self.nivel_microfono = 0.0
        self.solicitud_microfono_pendiente = False
        self.actualizar_visual()

    def al_evento_voz(self, evento):
        tipo = evento.get("type")
        if tipo in {"hello", "state"}:
            estado = evento.get("state")
            if isinstance(estado, str) and estado in APARIENCIAS:
                self.estado_actual = estado
                detalle = evento.get("detail")
                self.detalle_actual = (
                    str(detalle).strip()
                    if detalle is not None and str(detalle).strip()
                    else apariencia_para(estado).texto
                )
                if estado not in {"dormido", "escuchando"}:
                    self.nivel_microfono = 0.0
                self.solicitud_microfono_pendiente = False
            nivel = evento.get("mic_level")
            if isinstance(nivel, (int, float)):
                self.nivel_microfono = max(0.0, min(1.0, float(nivel)))
        elif tipo == "mic_level":
            nivel = evento.get("level")
            if isinstance(nivel, (int, float)):
                self.nivel_microfono = max(0.0, min(1.0, float(nivel)))
        self.actualizar_visual()

    def actualizar_visual(self):
        apariencia = apariencia_para(self.estado_actual)
        icono = crear_icono(apariencia, self.nivel_microfono)
        texto = f"ASTRO · {self.detalle_actual}"
        self.indicador.actualizar(apariencia, self.nivel_microfono)
        self.bandeja.setIcon(icono)
        self.bandeja.setToolTip(texto)
        self.accion_estado.setText(self.detalle_actual)
        silenciado = self.estado_actual == "microfono_apagado"
        habilitado = self.voz_conectada and not self.solicitud_microfono_pendiente
        self.accion_microfono.setChecked(silenciado)
        self.accion_microfono.setText(
            "Reactivar micrófono" if silenciado else "Silenciar micrófono"
        )
        self.accion_microfono.setEnabled(habilitado)
        self.vista.actualizar_microfono(silenciado, habilitado)

    def alternar_microfono(self, _comprobado=False):
        if not self.voz_conectada or self.solicitud_microfono_pendiente:
            return
        silenciar = self.estado_actual != "microfono_apagado"
        self.solicitud_microfono_pendiente = True
        self.actualizar_visual()
        self.receptor.establecer_microfono(silenciar)

    def salir_gui(self):
        self.atajo.detener()
        self.receptor.detener()
        self.indicador.hide()
        self.bandeja.hide()
        QApplication.quit()

    def detener(self):
        self.atajo.detener()
        self.receptor.detener()

    def renovar_cookie(self):
        token = vinculacion.leer_token()
        if token is not None:
            self.inyectar_cookie(token)

    def inyectar_cookie(self, token):
        cookie = QNetworkCookie(vinculacion.NOMBRE_COOKIE.encode(), token.encode())
        cookie.setPath("/")
        cookie.setSecure(True)
        cookie.setHttpOnly(True)
        cookie.setSameSitePolicy(QNetworkCookie.SameSite.Strict)
        cookie.setExpirationDate(QDateTime.currentDateTime().addDays(30))
        self.perfil.cookieStore().setCookie(
            cookie,
            QUrl(vinculacion.url_base_configurada()),
        )

    def revocado(self):
        self.temporizador.stop()
        self.temporizador_cookie.stop()
        vinculacion.borrar_token()
        self.perfil.cookieStore().deleteAllCookies()
        self.vista.hide()
        self.vista.setUrl(QUrl("about:blank"))
        self.vincular()

    def vincular(self):
        dialogo = DialogoVinculacion()
        if dialogo.exec() == QDialog.DialogCode.Accepted:
            self.mostrar(dialogo.token)
        else:
            self.salir_gui()


def preparar_registro():
    """Con pythonw no hay consola: los errores se guardan en data/gui/gui.log."""
    if sys.stdout is None or sys.stderr is None:
        CARPETA_PERFIL.mkdir(parents=True, exist_ok=True)
        archivo = open(CARPETA_PERFIL / "gui.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = archivo


def main() -> int:
    preparar_registro()
    bloqueo = BloqueoInstancia(RUTA_BLOQUEO_APP)
    if not bloqueo.adquirir():
        return 0
    try:
        lanzar_independiente()
        aplicacion = QApplication(sys.argv)
        aplicacion.setQuitOnLastWindowClosed(False)
        estado = Aplicacion()
        aplicacion.aboutToQuit.connect(estado.detener)
        QTimer.singleShot(0, estado.iniciar)
        return aplicacion.exec()
    finally:
        bloqueo.liberar()


if __name__ == "__main__":
    raise SystemExit(main())
