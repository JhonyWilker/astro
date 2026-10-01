"""Aplicación de escritorio de ASTRO (fase 38b): vinculación del PC y sesión de la PWA.

Uso: python -m gui.app
"""
import sys
from pathlib import Path

from PySide6.QtCore import QDateTime, QThread, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from gui import vinculacion
from gui.vinculacion import ErrorVinculacion

CARPETA_PERFIL = Path(__file__).resolve().parents[1] / "data" / "gui"
INTERVALO_COMPROBACION_MS = 60_000


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
    """Ventana de la PWA. Cerrarla cierra la aplicación (la bandeja llega más adelante)."""

    def closeEvent(self, evento):
        QApplication.quit()
        super().closeEvent(evento)


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
        self.vista.setPage(QWebEnginePage(perfil, self.vista))
        self.vista.setWindowTitle("ASTRO")
        self.vista.resize(420, 800)
        self.hilo = None
        self.temporizador = QTimer()
        self.temporizador.setInterval(INTERVALO_COMPROBACION_MS)
        self.temporizador.timeout.connect(self.comprobar)

    def iniciar(self):
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
        self.vista.load(QUrl(vinculacion.URL_BASE))
        self.vista.show()
        self.temporizador.start()

    def inyectar_cookie(self, token):
        cookie = QNetworkCookie(vinculacion.NOMBRE_COOKIE.encode(), token.encode())
        cookie.setPath("/")
        cookie.setSecure(True)
        cookie.setHttpOnly(True)
        cookie.setSameSitePolicy(QNetworkCookie.SameSite.Strict)
        cookie.setExpirationDate(QDateTime.currentDateTime().addDays(30))
        self.perfil.cookieStore().setCookie(cookie, QUrl(vinculacion.URL_BASE))

    def revocado(self):
        self.temporizador.stop()
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
            QApplication.quit()


def preparar_registro():
    """Con pythonw no hay consola: los errores se guardan en data/gui/gui.log."""
    if sys.stdout is None or sys.stderr is None:
        CARPETA_PERFIL.mkdir(parents=True, exist_ok=True)
        archivo = open(CARPETA_PERFIL / "gui.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = archivo


def main():
    preparar_registro()
    aplicacion = QApplication(sys.argv)
    aplicacion.setQuitOnLastWindowClosed(False)
    estado = Aplicacion()
    QTimer.singleShot(0, estado.iniciar)
    sys.exit(aplicacion.exec())


if __name__ == "__main__":
    main()
