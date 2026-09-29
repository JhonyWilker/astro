# Clientes

Los clientes no contienen el cerebro de ASTRO. Se conectan por WebSocket al mismo núcleo que vive en el VPS y cada conexión mantiene su propio historial en memoria.

## Terminal

En PowerShell:

```powershell
$env:ASTRO_WS_URL="ws://100.123.43.31:8000/ws"
.\.venv\Scripts\python.exe -m clients.terminal
```

Escribe `salir` para cerrar. La variable `ASTRO_WS_URL` permite cambiar la dirección sin modificar código.

## Navegador

Abre esta dirección desde un dispositivo conectado a la red privada de Tailscale:

```text
http://100.123.43.31:8000/
```

La página es un cliente de diagnóstico mínimo para la fase 22a. La aplicación web instalable en el iPhone se construirá en la fase 22c.

## Acceso

El puerto 8000 está enlazado únicamente a la IP privada de Tailscale del VPS. No está publicado en la interfaz pública.

## PWA en el iPhone

La dirección principal de la app es:

```text
https://astro-vps.tailbee6db.ts.net/
```

Solo funciona en dispositivos autorizados del tailnet. Tailscale Serve termina HTTPS y reenvía las peticiones al núcleo local; no se usa Tailscale Funnel ni se publica la app en Internet.

Para instalarla:

1. Mantén Tailscale conectado.
2. Abre la dirección HTTPS en Safari.
3. Pulsa Compartir y «Añadir a pantalla de inicio».
4. Mantén activado «Abrir como app web» si aparece.
5. Pulsa «Añadir» y abre ASTRO desde su icono.

La PWA guarda en caché únicamente su interfaz estática. Las preguntas, respuestas y conversaciones no se almacenan en el navegador. El historial continúa en memoria mientras se mantiene la conexión WebSocket; una reconexión inicia una sesión nueva.

## Estado y notificaciones

El botón «Estado» muestra si el núcleo está en línea, el proveedor y el modelo activos, el tiempo que lleva funcionando y el número de conexiones WebSocket. En «Motor de IA» se eligen el proveedor principal, el respaldo, el modelo de cada uno, la conmutación automática y el tiempo antes de volver a probar el principal. Los cambios se guardan para todas las sesiones sin reiniciar ASTRO.

Durante una conversación, la PWA acumula peticiones, tokens y coste desde que se abrió la conexión. Si el proveedor cambia por una caída o por su recuperación, aparece un aviso en el chat y la conversación conserva el historial de esa sesión.

## Editar un mensaje

Cada mensaje confirmado de Jhony muestra «Editar». «Cancelar» recupera el texto original sin realizar una petición. «Guardar y rehacer» sustituye ese turno y elimina su respuesta y todos los mensajes posteriores, porque dependían del texto antiguo. El coste de esas peticiones permanece en el total de la sesión.

Mientras ASTRO responde no se puede editar. Después de una reconexión, los mensajes visibles de la sesión anterior quedan bloqueados porque su historial ya no existe en el nuevo WebSocket.

En la PWA instalada del iPhone, «Activar notificaciones» solicita permiso mediante una acción expresa de Jhony y registra ese dispositivo para recibir avisos Web Push. «Enviar prueba» comprueba la entrega y «Desactivar en ASTRO» elimina la suscripción del servidor y del dispositivo.

iOS solo admite estas notificaciones desde una app web añadida a la pantalla de inicio. ASTRO no guarda conversaciones en la suscripción: únicamente conserva los datos técnicos necesarios para entregar el aviso.

## Grabación de voz local

La captura del micrófono se ejecuta en el equipo que físicamente oye a Jhony, no en el VPS. Instala su dependencia opcional dentro del entorno virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
```

Para ver las entradas disponibles:

```powershell
.\.venv\Scripts\python.exe -m clients.grabar_audio --listar
```

Para grabar cinco segundos:

```powershell
.\.venv\Scripts\python.exe -m clients.grabar_audio --segundos 5
```

Se puede elegir otra entrada añadiendo `--dispositivo NUMERO`. En el portátil de Jhony, la entrada WASAPI número 12 capturó correctamente a 48 kHz durante la prueba de la fase 23. El número puede cambiar al conectar o desconectar dispositivos, por lo que debe comprobarse de nuevo con `--listar`.

El resultado predeterminado es `data/audio/prueba.wav`, en formato WAV mono PCM de 16 bits. La carpeta `data` está excluida de Git porque puede contener voz privada.

## Conversación de voz manual

La fase 26 une la captura, la transcripción, el núcleo remoto y la síntesis en una sola sesión. En el portátil probado:

```powershell
$env:ASTRO_WS_URL="wss://astro-vps.tailbee6db.ts.net/ws"
.\.venv\Scripts\python.exe -m clients.voz --microfono 1 --altavoz 3
```

Pulsa Enter, habla y espera la respuesta. El cliente conserva unos instantes anteriores al inicio de la voz y termina automáticamente después de 1 segundo de silencio. Puedes repetir sin perder el historial; escribe `salir` en lugar de pulsar solo Enter para cerrar.

La espera inicial máxima es de 5 segundos y una intervención puede durar hasta 30 segundos. Se pueden ajustar con `--espera-maxima`, `--duracion-maxima` y `--silencio-final`. Los límites evitan que el micrófono quede abierto indefinidamente.

Los números de los dispositivos pueden cambiar. Usa `python -m clients.grabar_audio --listar` para revisar micrófonos y las herramientas de `sounddevice` para revisar salidas. La detección usa el nivel de la señal y se adapta al ruido observado antes de que comience la voz.

## Respuesta de voz en streaming

ASTRO no espera a recibir todo el texto. El primer fragmento se sintetiza en cuanto termina una frase o se acumulan unos 45 caracteres; mientras ese audio se reproduce, el siguiente se prepara. La terminal muestra el tiempo desde que termina la captura hasta antes de llamar al reproductor y el número de fragmentos hablados. Esta aproximación excluye el silencio final del detector y la latencia del dispositivo; no es una medición acústica de la primera palabra.

Los WAV parciales se guardan en `data/audio` y continúan excluidos de Git. El orden de la respuesta se conserva aunque síntesis y reproducción trabajen simultáneamente.

## Interrumpir una respuesta hablada

Hasta que la fase 34 incorpore cancelación de eco, esta función debe probarse con auriculares:

```powershell
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1 --interrumpir-con-voz
```

Cuando Jhony habla encima, el cliente corta el audio local, descarta los fragmentos pendientes y envía `cancel` al núcleo. El historial conserva únicamente el último fragmento reproducido por completo; una herramienta que ya terminó no se revierte. La terminal muestra en milisegundos el tiempo entre detectar la voz y detener la reproducción.
