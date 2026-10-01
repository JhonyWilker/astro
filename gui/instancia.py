"""Bloqueos de instancia liberados automáticamente por el sistema operativo."""

import os
from pathlib import Path
from typing import BinaryIO


class BloqueoInstancia:
    """Impide duplicados sin depender de archivos PID que puedan quedar obsoletos."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)
        self._archivo: BinaryIO | None = None

    def adquirir(self) -> bool:
        if self._archivo is not None:
            return True
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        archivo = self.ruta.open("a+b")
        archivo.seek(0, os.SEEK_END)
        if archivo.tell() == 0:
            archivo.write(b"0")
            archivo.flush()
        archivo.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            archivo.close()
            return False
        self._archivo = archivo
        return True

    def liberar(self) -> None:
        archivo = self._archivo
        if archivo is None:
            return
        self._archivo = None
        try:
            archivo.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
        finally:
            archivo.close()

    def __enter__(self):
        if not self.adquirir():
            raise RuntimeError("Ya existe otra instancia")
        return self

    def __exit__(self, _tipo, _valor, _traza) -> None:
        self.liberar()
