# gui

Aplicación de escritorio de ASTRO (bloque 2b). Una ventana de PySide6 que carga la PWA del VPS y se identifica como dispositivo propio del PC.

- `vinculacion.py`: canje del código de un solo uso, token en el almacén de credenciales de Windows y comprobación de que el servidor sigue aceptándolo.
- `app.py`: diálogo de vinculación, sesión de la PWA y vuelta a vincular si el dispositivo se revoca.

- `monitor.py`: receptor mínimo del puente local de voz (fase 38c); imprime los eventos en tiempo real.

Dependencias: `requirements-gui.txt`.

Puente de voz, en dos terminales:

```
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1 --puente
.\.venv\Scripts\python.exe -m gui.monitor
```

Arranque, sin consola:

```
.\.venv\Scripts\pythonw.exe -m gui.app
```

Con `pythonw` los errores se guardan en `data/gui/gui.log`. El arranque con el PC y el acceso directo llegan en la fase 38j.
