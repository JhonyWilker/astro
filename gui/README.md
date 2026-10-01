# gui

Aplicación de escritorio de ASTRO (bloque 2b). La ventana PySide6 carga la PWA y un supervisor independiente mantiene el cliente local de voz.

- `vinculacion.py`: canje del código de un solo uso, token en el almacén de credenciales de Windows y comprobación de que el servidor sigue aceptándolo.
- `app.py`: diálogo de vinculación, sesión de la PWA y vuelta a vincular si el dispositivo se revoca.
- `instancia.py`: bloqueo exclusivo de la ventana, el supervisor y la voz.
- `supervisor.py`: inicia `clients.voz --activacion --puente`, lo vigila y limita los reinicios.

- `monitor.py`: receptor mínimo del puente local de voz (fase 38c); imprime los eventos en tiempo real.

Dependencias: `requirements-gui.txt`.

Puente de voz, en dos terminales:

```
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1 --puente
.\.venv\Scripts\python.exe -m gui.monitor
```

Arranque completo, sin consola:

```
.\.venv\Scripts\pythonw.exe -m gui.app
```

Con `pythonw` los errores se guardan en `data/gui/gui.log`. El arranque con el PC y el acceso directo llegan en la fase 38j.

La ventana, el supervisor y la voz son procesos separados. Cerrar la ventana no detiene la escucha. El estado del supervisor queda en `data/gui/supervisor.json`; sus incidencias se guardan en `data/gui/supervisor.log` y la salida de voz en `data/gui/voz.log`. Una salida normal de la voz no se reinicia; los fallos se reintentan como máximo tres veces en 60 segundos.
