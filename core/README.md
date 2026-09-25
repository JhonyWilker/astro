# Core

Cerebro de ASTRO: bucle principal, contexto y decisiones.

## Chat de un turno

`chat.py` pide una pregunta en la terminal, la envía al modelo configurado en `.env` y muestra la respuesta.

```powershell
.\.venv\Scripts\python.exe .\core\chat.py
```

En la fase 11 cada ejecución contiene un único intercambio. El historial se añadirá en la fase 12.
