"""Representación visual del estado real de la voz de ASTRO."""
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True)
class AparienciaEstado:
    texto: str
    color: str


APARIENCIAS = {
    "desconectado": AparienciaEstado("Voz no disponible", "#64748b"),
    "microfono_apagado": AparienciaEstado("Micrófono apagado", "#ef4444"),
    "dormido": AparienciaEstado("Esperando «Astro»", "#38bdf8"),
    "escuchando": AparienciaEstado("Escuchando", "#22c55e"),
    "pensando": AparienciaEstado("Pensando", "#a78bfa"),
    "ejecutando": AparienciaEstado("Usando una herramienta", "#f59e0b"),
    "hablando": AparienciaEstado("Hablando", "#06b6d4"),
}


def apariencia_para(estado: str | None) -> AparienciaEstado:
    return APARIENCIAS.get(estado or "desconectado", APARIENCIAS["desconectado"])


def crear_icono(apariencia: AparienciaEstado, nivel: float = 0.0) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(apariencia.color)
    pintor.setPen(QPen(color.lighter(145), 4))
    pintor.drawArc(QRectF(5, 5, 54, 54), 90 * 16, -round(360 * 16 * nivel))
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(color)
    pintor.drawEllipse(QRectF(14, 14, 36, 36))
    pintor.end()
    return QIcon(pixmap)


class IndicadorFlotante(QWidget):
    activado = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setToolTip(APARIENCIAS["desconectado"].texto)
        self.setFixedSize(92, 92)
        self.apariencia = APARIENCIAS["desconectado"]
        self.nivel = 0.0
        self._desplazamiento = None
        self._origen_arrastre = None

    def mostrar_en_esquina(self) -> None:
        pantalla = QApplication.primaryScreen()
        if pantalla is not None:
            zona = pantalla.availableGeometry()
            self.move(zona.right() - self.width() - 18, zona.bottom() - self.height() - 18)
        self.show()

    def actualizar(self, apariencia: AparienciaEstado, nivel: float) -> None:
        self.apariencia = apariencia
        self.nivel = max(0.0, min(1.0, nivel))
        self.setToolTip(apariencia.texto)
        self.update()

    def paintEvent(self, _evento) -> None:
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.apariencia.color)
        halo = QRadialGradient(46, 46, 45)
        transparente = QColor(color)
        transparente.setAlpha(0)
        suave = QColor(color)
        suave.setAlpha(115)
        halo.setColorAt(0.55, suave)
        halo.setColorAt(1.0, transparente)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(halo)
        pintor.drawEllipse(QRectF(1, 1, 90, 90))
        pintor.setPen(QPen(color.lighter(155), 5))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawArc(
            QRectF(8, 8, 76, 76),
            90 * 16,
            -round(360 * 16 * self.nivel),
        )
        pintor.setPen(QPen(color.lighter(175), 2))
        pintor.setBrush(color.darker(135))
        pintor.drawEllipse(QRectF(23, 23, 46, 46))

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            posicion = evento.globalPosition().toPoint()
            self._origen_arrastre = posicion
            self._desplazamiento = posicion - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, evento) -> None:
        if self._desplazamiento is not None:
            self.move(evento.globalPosition().toPoint() - self._desplazamiento)

    def mouseReleaseEvent(self, evento) -> None:
        if (
            evento.button() == Qt.MouseButton.LeftButton
            and self._origen_arrastre is not None
            and (evento.globalPosition().toPoint() - self._origen_arrastre).manhattanLength() < 6
        ):
            self.activado.emit()
        self._desplazamiento = None
        self._origen_arrastre = None

