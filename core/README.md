# Core

Cerebro de ASTRO: bucle principal, contexto y decisiones.

## Chat con historial durante la sesión

`chat.py` mantiene una conversación en la terminal. Cada pregunta y respuesta se añade a una lista y se envía en el turno siguiente para conservar el contexto.

```powershell
.\.venv\Scripts\python.exe .\core\chat.py
```

Escribe `salir` para terminar. El historial solo vive en memoria: al cerrar el programa desaparece. La memoria entre sesiones se añadirá en el bloque 3.

## Personalidad

Al arrancar, `chat.py` carga `config/personality.md` y lo envía a la API como instrucciones del asistente. El archivo contiene comportamiento, no claves ni contraseñas.

## Respuestas en streaming

ASTRO muestra cada fragmento de texto en cuanto llega desde la API, sin esperar a que termine la respuesta completa. Al finalizar, une los fragmentos y guarda el texto completo en el historial de la conversación.
