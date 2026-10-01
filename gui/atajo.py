"""Atajo global de Windows para alternar el silencio del micrófono."""
import ctypes
import ctypes.wintypes as wt
import threading

from PySide6.QtCore import QObject, Signal


ID_ATAJO = 0xA570
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class AtajoSilencio(QObject):
    activado = Signal()

    def __init__(self):
        super().__init__()
        self._hilo = None
        self._id_hilo = None
        self._listo = threading.Event()
        self.registrado = False

    def iniciar(self) -> bool:
        if self._hilo is not None and self._hilo.is_alive():
            return self.registrado
        self._listo.clear()
        self._hilo = threading.Thread(
            target=self._escuchar,
            name="atajo-silencio",
            daemon=True,
        )
        self._hilo.start()
        self._listo.wait(timeout=2.0)
        return self.registrado

    def detener(self) -> None:
        if self._id_hilo is not None:
            ctypes.windll.user32.PostThreadMessageW(
                self._id_hilo,
                WM_QUIT,
                0,
                0,
            )
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)

    def _escuchar(self) -> None:
        user32 = ctypes.windll.user32
        self._id_hilo = ctypes.windll.kernel32.GetCurrentThreadId()
        self.registrado = bool(user32.RegisterHotKey(
            None,
            ID_ATAJO,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
            ord("S"),
        ))
        self._listo.set()
        if not self.registrado:
            return
        mensaje = wt.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(mensaje), None, 0, 0) > 0:
                if mensaje.message == WM_HOTKEY and mensaje.wParam == ID_ATAJO:
                    self.activado.emit()
        finally:
            user32.UnregisterHotKey(None, ID_ATAJO)
            self.registrado = False
