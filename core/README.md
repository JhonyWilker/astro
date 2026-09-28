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

Una clave ausente invalida únicamente la ruta de ese proveedor. Si existe otra ruta disponible, ASTRO continúa con ella; si ninguna puede prepararse, devuelve un error controlado sin cerrar el WebSocket.

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
- `POST /auth/login`: vincula una clave de dispositivo y crea una cookie segura.
- `POST /auth/pairings`: crea una vinculación temporal mediante QR y código; solo para administradores.
- `POST /auth/pair/claim`: reclama una vinculación temporal y crea la cookie segura del dispositivo.
- `GET /auth/devices`: lista nombres, roles y estados sin devolver credenciales; solo para administradores.
- `PATCH /auth/devices/{id}`: cambia el rol o reactiva un dispositivo; solo para administradores.
- `DELETE /auth/devices/{id}`: revoca un dispositivo; solo para administradores.
- `POST /auth/logout`: elimina la cookie de acceso del navegador.
- `GET /`: aplicación web instalable.
- `WS /ws`: conversación en streaming.

La carcasa estática y `/health` son públicos dentro de la red privada. Las demás rutas y el WebSocket exigen una credencial declarada en `.env.acceso`. El servidor valida el origen web, limita cuerpos y tramas a 16 KiB, aplica límites de frecuencia y reserva los ajustes de IA y la prueba Push a dispositivos administradores. El navegador entrega una vez su clave a `/auth/login` y recibe una cookie `Secure`, `HttpOnly` y `SameSite=Strict`; los clientes Python usan `Bearer`.

Como alternativa, un administrador puede abrir «Añadir dispositivo» en el panel Estado y generar un QR y un código de ocho cifras. Ambos representan la misma vinculación, caducan a los cinco minutos y solo pueden usarse una vez. Antes de generarlos se elige un rol: administrador y personal comparten la identidad y conversación de Jhony; restringido recibe identidad, historial y personalidad aislados, no administra ASTRO y solo dispone de herramientas expresamente permitidas. El QR transporta el código en el fragmento de la URL, que no se envía al servidor durante la navegación. El registro persistente conserva el identificador, nombre, rol, estado, identidad interna y huella SHA-256 del token definitivo, no el token original.

El panel permite cambiar el rol, reactivar y revocar otros dispositivos. No permite cambiar ni revocar el dispositivo administrador desde el que se realiza la operación. Si una conexión WebSocket abierta pierde acceso o cambia de identidad, el servidor la cierra para que reconecte con sus permisos actuales.

El protocolo 2 envía `ready` al conectar, uno o más `delta`, `provider_change` cuando cambia la ruta y `done` al terminar. El cliente confirma contenido con `ack` y `played`; puede enviar `cancel` y recibe `cancelled`. `busy` evita dos turnos simultáneos y `sync` actualiza otros dispositivos. Una edición entra como `edit`; si termina, el servidor envía `rewind` antes de la respuesta corregida. Los fallos se envían como `error`.

`core/conversaciones.py` asigna una conversación al usuario autenticado, no al socket. Voz, PWA y reconexiones comparten historial, con un solo turno activo a la vez. Al cancelar, ASTRO cierra el stream cuando el proveedor lo permite y conserva únicamente el prefijo confirmado por el cliente; las herramientas ya terminadas no se deshacen. El despliegue usa un único proceso de Uvicorn porque el historial continúa en memoria: reiniciar el VPS lo borra y la persistencia llegará en el bloque de memoria.

## Aplicación web instalable

`clients/web` contiene la PWA de ASTRO: HTML accesible, estilos adaptados al iPhone, cliente WebSocket seguro, manifiesto, service worker e icono SVG. La app muestra el streaming, el uso y coste acumulados de la sesión, el estado de conexión y reconecta automáticamente. Su panel «Estado» también permite administrar el motor de IA.

Cada mensaje confirmado de Jhony ofrece «Editar». Al guardar, el servidor reconstruye el historial hasta el turno anterior, genera la nueva respuesta y solo entonces confirma a la PWA que debe eliminar ese mensaje y todos los posteriores. Si la generación falla, conserva el historial original. Cancelar no realiza ninguna petición; el coste ya consumido permanece acumulado.

El service worker cachea solo la carcasa visual para que la interfaz pueda abrirse aunque la red tarde. No intercepta el WebSocket ni guarda conversaciones. La URL preferida es `https://astro-vps.tailbee6db.ts.net/`.

El cliente de voz acepta `--interrumpir-con-voz` para escuchar mientras reproduce y enviar `cancel` cuando Jhony habla encima. Hasta incorporar cancelación de eco en la fase 34, esta opción debe usarse con auriculares para que ASTRO no confunda su propia voz con una interrupción.

## Notificaciones Web Push

`core/notificaciones.py` valida y conserva las suscripciones en `data/push_subscriptions.json`. El archivo contiene direcciones y claves técnicas del servicio Push, pero no preguntas, respuestas ni conversaciones.

Los avisos se firman mediante VAPID. La clave pública puede entregarse al navegador; la privada se monta como secreto de Docker y nunca se guarda en Git. Las suscripciones expiradas se eliminan automáticamente cuando el servicio Push responde con 404 o 410.
