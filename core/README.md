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

`chat.py` lee `config/config.yaml` al arrancar. El archivo define los proveedores disponibles, sus modelos predeterminados, el idioma habitual, el máximo de tokens de salida y cuántos turnos se envían como contexto. Los valores se validan antes de realizar peticiones a la API.

## Proveedores de IA

OpenAI es el proveedor principal predeterminado y OpenRouter es su respaldo. El panel «Estado» de la PWA permite cambiar el proveedor principal, el respaldo, sus modelos, la conmutación automática y el tiempo de recuperación sin editar código ni reiniciar ASTRO.

La selección se guarda en `data/ajustes_ia.json`, fuera de Git. `config/config.yaml` conserva los valores iniciales que se usan cuando todavía no existe ese archivo.

Cada proveedor declara en el YAML su nombre visible, URL base, modelo predeterminado y nombre de la variable que contiene su clave. Las claves `OPENAI_API_KEY` y `OPENROUTER_API_KEY` viven exclusivamente en `.env`; nunca se escriben en el YAML, en los ajustes ni en el código.

Si el principal falla por conexión, timeout, límite, autenticación o error del servidor, ASTRO termina ese turno con el respaldo. Ambos proveedores reciben el historial de la sesión. Si la caída ocurre durante el streaming, el respaldo recibe además el fragmento ya visible y continúa desde él. Los resultados de herramientas ya completadas se reutilizan sin ejecutarlas otra vez. Tras el tiempo configurado, un turno nuevo prueba el principal y vuelve a él automáticamente si responde. Los errores de una petición inválida no activan el respaldo.

## Uso, coste y tiempo

Cada petición terminada añade metadatos a `logs/uso.jsonl`: proveedor, modelo, nivel de servicio, tokens, duración y coste estimado. No se guarda el contenido de la conversación.

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

## Registro de herramientas

`tools/registro.py` descubre automáticamente los archivos de herramientas y ofrece sus contratos a la API. El cerebro ejecuta cualquier herramienta registrada mediante la misma interfaz, sin importar su nombre concreto. Cada ficha incluye nombre, descripción, parámetros y riesgo.

## Bucle de agente

Dentro de un turno, ASTRO puede alternar varias veces entre el modelo y las herramientas. Cada resultado se añade al contexto de trabajo para que el modelo decida el paso siguiente, hasta producir una respuesta sin nuevas llamadas.

El número máximo de ejecuciones se define en `agente.pasos_herramienta_maximos`. Al alcanzarlo, ASTRO detiene la tarea para evitar bucles y gasto inesperado. Las herramientas se ejecutan de una en una y en orden.

## API y WebSocket

`core/api.py` publica el mismo núcleo mediante FastAPI:

- `GET /health`: comprobación mínima de salud.
- `GET /status`: versión, proveedor, modelo, tiempo activo, conexiones y estado de Web Push.
- `GET /ai/settings`: estado y opciones del motor de IA junto con un token CSRF efímero.
- `PUT /ai/settings`: valida y guarda los ajustes del motor de IA; requiere el token CSRF.
- `GET /push/public-key`: clave pública VAPID para registrar el dispositivo.
- `POST /push/subscribe`: registra o actualiza una suscripción.
- `POST /push/unsubscribe`: elimina una suscripción.
- `POST /push/test`: envía un aviso de prueba a los dispositivos registrados.
- `GET /`: aplicación web instalable.
- `WS /ws`: conversación en streaming.

El servidor envía `ready` al conectar, uno o más mensajes `delta` durante la respuesta, `provider_change` cuando cambia la ruta y `done` al terminar, con el uso agregado del turno y el proveedor que completó la respuesta. Los fallos se envían como `error`.

Cada WebSocket crea una `SesionASTRO` independiente. `core/sesion.py` comparte la configuración, la personalidad y el registro de herramientas, pero conserva el historial por conexión para que dos clientes no mezclen sus conversaciones.

El despliegue usa un único proceso de Uvicorn porque el historial todavía vive en memoria. La persistencia compartida llegará en el bloque de memoria.

## Aplicación web instalable

`clients/web` contiene la PWA de ASTRO: HTML accesible, estilos adaptados al iPhone, cliente WebSocket seguro, manifiesto, service worker e icono SVG. La app muestra el streaming, el uso y coste acumulados de la sesión, el estado de conexión y reconecta automáticamente. Su panel «Estado» también permite administrar el motor de IA.

El service worker cachea solo la carcasa visual para que la interfaz pueda abrirse aunque la red tarde. No intercepta el WebSocket ni guarda conversaciones. La URL preferida es `https://astro-vps.tailbee6db.ts.net/`.

## Notificaciones Web Push

`core/notificaciones.py` valida y conserva las suscripciones en `data/push_subscriptions.json`. El archivo contiene direcciones y claves técnicas del servicio Push, pero no preguntas, respuestas ni conversaciones.

Los avisos se firman mediante VAPID. La clave pública puede entregarse al navegador; la privada se monta como secreto de Docker y nunca se guarda en Git. Las suscripciones expiradas se eliminan automáticamente cuando el servicio Push responde con 404 o 410.
