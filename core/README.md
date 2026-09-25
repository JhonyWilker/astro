# Core

Cerebro de ASTRO: bucle principal, contexto y decisiones.

## Chat con historial durante la sesión

`chat.py` mantiene una conversación en la terminal. Cada pregunta y respuesta se añade a una lista y se envía en el turno siguiente para conservar el contexto.

```powershell
.\.venv\Scripts\python.exe -m core.chat
```

Escribe `salir` para terminar. El historial solo vive en memoria: al cerrar el programa desaparece. La memoria entre sesiones se añadirá en el bloque 3.

## Personalidad

Al arrancar, `chat.py` carga `config/personality.md` y lo envía a la API como instrucciones del asistente. El archivo contiene comportamiento, no claves ni contraseñas.

## Respuestas en streaming

ASTRO muestra cada fragmento de texto en cuanto llega desde la API, sin esperar a que termine la respuesta completa. Al finalizar, une los fragmentos y guarda el texto completo en el historial de la conversación.

## Configuración central

`chat.py` lee `config/config.yaml` al arrancar. El archivo decide el modelo, el idioma habitual, el máximo de tokens de salida y cuántos turnos se envían como contexto. Los valores se validan antes de realizar peticiones a la API.

## Uso, coste y tiempo

Cada petición terminada añade metadatos a `logs/uso.jsonl`: modelo, nivel de servicio, tokens, duración y coste estimado. No se guarda el contenido de la conversación.

Tras cada respuesta aparece un resumen. El informe del día se muestra al salir o puede consultarse con:

```powershell
.\.venv\Scripts\python.exe -m core.uso
```

El coste es una estimación calculada con las tarifas de `config/config.yaml`; la factura de OpenAI es la referencia definitiva.

## Errores y reintentos

El SDK de OpenAI usa el timeout y los reintentos definidos en `config/config.yaml`. ASTRO no añade otro bucle de reintentos, para evitar peticiones multiplicadas o respuestas duplicadas después de iniciar el streaming.

Si la petición sigue fallando, ASTRO explica el problema y continúa abierto. `logs/errores.jsonl` conserva únicamente metadatos técnicos; no guarda conversaciones ni mensajes completos de la excepción.

## Herramienta de fecha y hora

Cuando una pregunta depende de la fecha o la hora actuales, el modelo solicita `obtener_fecha_hora`. Python consulta el reloj en la zona definida por `zona_horaria` en `config/config.yaml` y devuelve el resultado al modelo para que redacte la respuesta. Un turno con esta herramienta consume y registra dos peticiones: la decisión de usarla y la respuesta final.

## Calculadora

Cuando Jhony pide un cálculo, el modelo solicita `calcular` con una expresión. Python acepta solo números, paréntesis y operadores aritméticos, conserva enteros y fracciones exactos y devuelve también una representación decimal. No se usa `eval` ni se permite ejecutar código.
