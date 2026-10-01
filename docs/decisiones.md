# Decisiones de ASTRO

Las decisiones importantes del proyecto se registran aquí para conservar su contexto y evitar contradicciones futuras.

---

## 2026-09-24 · ChatGPT como proveedor inicial del modelo

- Contexto: El plan mencionaba Claude y Anthropic, pero Jhony decidió que el cerebro de ASTRO use ChatGPT.
- Decisión: Usar la API de ChatGPT como proveedor inicial del modelo de lenguaje.
- Motivo: Mantener una única elección clara para el desarrollo de ASTRO.
- Consecuencia: El núcleo conservará una capa propia para poder cambiar de modelo en el futuro sin rehacer el sistema, pero no se cambiará de proveedor sin una nueva decisión de Jhony.

## 2026-09-25 · Proyecto de OpenAI y control de gasto

- Contexto: ASTRO necesita acceder a la API sin mezclar consumo ni credenciales con otros proyectos.
- Decisión: Crear un proyecto independiente llamado `ASTRO`, usar una clave restringida a peticiones al modelo y guardarla solo en `.env`. Configurar un límite duro de 50 USD al mes, alertas al 80 % y al 100 %, y mantener desactivada la recarga automática.
- Motivo: Limitar el impacto de una posible filtración, controlar el gasto y separar claramente el consumo de ASTRO.
- Consecuencia: Al llegar a 50 USD las nuevas peticiones comenzarán a fallar con error 429, aunque OpenAI advierte que el corte puede tener un pequeño retraso. La clave no caduca por decisión de Jhony, por lo que deberá revocarse y sustituirse si se sospecha una filtración.

## 2026-09-25 · VPS, acceso privado y copias externas

- Contexto: ASTRO necesita un servidor europeo disponible 24/7. Hetzner bloqueó la creación del proyecto hasta completar una verificación de identidad que Jhony no podía hacer en ese momento.
- Decisión: Usar un Hostinger KVM 2 con pago mensual, Ubuntu 26.04.1 LTS limpio, acceso SSH con clave únicamente a través de Tailscale y UFW sin entradas públicas. Guardar copias diarias cifradas con restic en Google Drive mediante rclone con permiso `drive.file`, conservando 7 diarias, 4 semanales y 6 mensuales.
- Motivo: Poder continuar sin debilitar la seguridad, pagar mes a mes y mantener una copia externa económica y restaurable.
- Consecuencia: El primer mes del VPS cuesta 12,09 € con IVA y la renovación indicada es 21,49 € al mes antes de IVA, aproximadamente 26 € con IVA. Este coste se añade al límite de 50 USD de OpenAI, que Jhony decidió no reducir, por lo que el total puede superar los 50 € iniciales. Monarx y el administrador de Docker de Hostinger quedan desactivados; Docker se instalará manualmente solo cuando una fase lo necesite.

## 2026-09-25 · Identidad y personalidad de ASTRO

- Contexto: ASTRO necesita mantener un estilo reconocible y coherente en todas sus respuestas sin depender de que Jhony repita preferencias en cada mensaje.
- Decisión: Cargar `config/personality.md` como instrucciones del modelo. ASTRO tendrá identidad propia, hablará en masculino, usará español de España por defecto, llamará «Jhony» a su usuario y mantendrá un tono sereno, inteligente, elegante, directo y discreto, con humor seco ocasional.
- Motivo: Separar la personalidad permanente del historial de conversación permite revisarla y conservar un comportamiento coherente.
- Consecuencia: ASTRO no afirmará ser ni copiará la identidad, frases o voz de JARVIS, FRIDAY, otros personajes o personas reales; tampoco inventará capacidades, hechos ni acciones.

## 2026-09-25 · Configuración central sin secretos

- Contexto: El modelo estaba definido mediante una variable de entorno y el idioma dentro de la personalidad, lo que repartía la configuración entre varios lugares.
- Decisión: Usar `config/config.yaml` como única fuente para el modelo, el idioma habitual, el máximo de tokens de salida y los turnos de historial. Reservar `.env` exclusivamente para secretos.
- Motivo: Permitir ajustes operativos sin tocar Python y detectar valores inválidos antes de llamar a la API.
- Consecuencia: ASTRO debe reiniciarse después de editar el YAML. La configuración inicial es `gpt-6-astra`, español de España, 2000 tokens de salida y 20 turnos de historial; cualquier valor vacío, ausente o no positivo impide el arranque.

## 2026-09-25 · Proveedores de IA intercambiables

- Contexto: El modelo de OpenAI ya puede cambiarse desde `config/config.yaml`, pero el núcleo depende actualmente del cliente de OpenAI.
- Decisión: Añadir la fase 22e para crear una interfaz común y seleccionar proveedor y modelo desde la configuración, manteniendo OpenAI como proveedor inicial.
- Motivo: Permitir que Jhony alterne entre proveedores compatibles sin modificar el núcleo de ASTRO.
- Consecuencia: Solo podrán seleccionarse sin código los proveedores que tengan un adaptador implementado. Cada proveedor nuevo requerirá crear su adaptador una vez y guardar su clave exclusivamente en `.env`; la elección del segundo proveedor se hará en la fase 22e.

## 2026-09-25 · Registro privado de uso y coste estimado

- Contexto: ASTRO necesita mostrar cuánto consume cada petición y producir un informe diario sin guardar todavía conversaciones ni introducir una base de datos antes de la fase prevista.
- Decisión: Guardar una línea JSON por petición en `logs/uso.jsonl` con fecha, modelo, nivel de servicio, tokens, tiempo y coste estimado. El archivo es local, está ignorado por Git y no contiene preguntas ni respuestas.
- Motivo: Obtener datos reales de consumo y latencia con un formato sencillo, auditable y reemplazable cuando llegue la base de datos.
- Consecuencia: El cálculo usa las tarifas por millón de tokens de `config/config.yaml` y fuerza el nivel estándar `default`. Los precios deben revisarse al cambiar de modelo o tarifa; la factura de OpenAI prevalece sobre la estimación local.

## 2026-09-25 · Reintentos limitados y sin duplicar streams

- Contexto: Los fallos temporales deben recuperarse cuando sea posible, pero combinar reintentos propios con los del SDK podría multiplicar peticiones y duplicar una respuesta parcialmente mostrada.
- Decisión: Usar exclusivamente los reintentos automáticos del SDK, configurados en 2 con un timeout de 30 segundos por intento. Después de agotarlos, ASTRO informa del tipo de problema y continúa abierto.
- Motivo: Recuperar errores transitorios sin generar bucles, gasto inesperado ni texto duplicado.
- Consecuencia: Una respuesta interrumpida después de comenzar el streaming nunca se repite automáticamente. Los metadatos del fallo se guardan localmente sin conversaciones ni mensajes completos de excepción.

## 2026-09-25 · Fecha y hora local como herramienta

- Contexto: El modelo no debe adivinar la fecha ni depender de información potencialmente desactualizada, y ASTRO necesita respetar los cambios de horario de España.
- Decisión: Configurar `Europe/Madrid` en `config/config.yaml` y obtener la fecha y hora mediante una herramienta local de Python basada en `zoneinfo` y `tzdata`.
- Motivo: Separar el dato real de la redacción del modelo produce respuestas verificables y aplica automáticamente el horario de invierno y de verano.
- Consecuencia: Una consulta temporal usa dos peticiones a la API, ambas registradas: una para elegir la herramienta y otra para redactar con su resultado. Cambiar de zona no requiere modificar código.

## 2026-09-25 · Calculadora exacta y sin ejecución de código

- Contexto: El modelo puede cometer errores aritméticos y evaluar texto arbitrario con `eval` permitiría ejecutar código dentro de ASTRO.
- Decisión: Resolver expresiones mediante un recorrido limitado del árbol `ast`, usando `Fraction` y `Decimal`, sin `eval`.
- Motivo: Obtener resultados reproducibles y exactos mientras se impide el acceso a nombres, funciones, archivos u otras capacidades de Python.
- Consecuencia: Solo se aceptan los operadores aritméticos documentados y se limitan longitud, exponentes y tamaño del resultado. Las operaciones no permitidas producen un error controlado.

## 2026-09-25 · Registro desacoplado de herramientas

- Contexto: El núcleo importaba y ejecutaba cada herramienta por nombre, de modo que añadir una nueva exigía modificar `core/chat.py`.
- Decisión: Cada archivo de herramienta exportará una ficha `HERRAMIENTA` con nombre, descripción, parámetros, riesgo y ejecutor; un registro la descubrirá automáticamente al arrancar.
- Motivo: Mantener el cerebro independiente de herramientas concretas y convertir cada incorporación en un cambio localizado y verificable.
- Consecuencia: Un archivo de herramienta incompleto o un nombre duplicado impiden el arranque con un error claro. Los niveles bajo, medio y alto quedan disponibles como metadatos, pero su política de autorización se implementará en la fase 53.

## 2026-09-25 · Bucle de agente secuencial y acotado

- Contexto: Resolver tareas dependientes requiere que el modelo observe el resultado de una herramienta antes de elegir la siguiente, pero un bucle sin límite puede disparar coste o no terminar.
- Decisión: Mantener una entrada de trabajo acumulada, ejecutar herramientas secuencialmente y limitar cada turno a 5 ejecuciones configurables.
- Motivo: Permitir planes de varios pasos con resultados dependientes, conservando orden, trazabilidad y un tope de seguridad.
- Consecuencia: Cada vuelta a la API tiene su propio registro de uso. Tras alcanzar el límite se permite únicamente la respuesta final; si el modelo solicita otra herramienta, ASTRO detiene el turno con un mensaje controlado.

## 2026-09-25 · Suite rápida sin red ni secretos

- Contexto: Las pruebas manuales y las llamadas reales a la API son lentas, cuestan dinero y pueden fallar por causas externas.
- Decisión: Mantener una suite pytest determinista que sustituya la API por dobles de prueba, escriba solo en carpetas temporales y no cargue secretos.
- Motivo: Detectar regresiones del núcleo en segundos, con el mismo resultado en el portátil, GitHub o el VPS.
- Consecuencia: `python -m pytest` será la comprobación mínima antes de cerrar cambios del núcleo. Las pruebas de integración real seguirán siendo separadas y cada fallo corregido deberá añadir o reforzar una prueba automática.

## 2026-09-25 · Núcleo único desplegado en el VPS

- Contexto: La terminal y la web deben hablar con el mismo ASTRO disponible 24/7, sin exponer el servicio a Internet ni mezclar historiales entre usuarios o conexiones.
- Decisión: Ejecutar un único núcleo FastAPI con WebSocket dentro de Docker en el VPS. Publicar el puerto 8000 solo en la IP de Tailscale, usar una sesión en memoria por WebSocket y mantener un único proceso de Uvicorn mientras el historial no sea persistente.
- Motivo: Centralizar personalidad, herramientas, configuración y uso en un solo servicio, conservando aislamiento entre clientes y una superficie de red privada.
- Consecuencia: El portátil ya no necesita ejecutar el cerebro para conversar con ASTRO. El contenedor se reinicia automáticamente y está endurecido con usuario sin privilegios, raíz de solo lectura, capacidades eliminadas y secretos fuera de Git; reiniciar el servicio borra las conversaciones actuales hasta que se implemente la memoria persistente.

## 2026-09-25 · Acceso móvil privado mediante Tailscale

- Contexto: Jhony necesita usar ASTRO desde el iPhone fuera de casa sin publicar el núcleo en Internet ni depender de la red del restaurante o del hogar.
- Decisión: Incorporar el iPhone al mismo tailnet que el portátil y el VPS, y acceder al cliente web mediante la IP privada estable `100.123.43.31`.
- Motivo: Tailscale cifra el tráfico entre dispositivos y permite cambiar entre Wi‑Fi y datos móviles sin abrir puertos públicos.
- Consecuencia: ASTRO solo responde a dispositivos autorizados del tailnet. Tailscale debe permanecer conectado en el iPhone; la conexión puede usar un repetidor cifrado cuando las redes no permiten un enlace directo, con algo más de latencia pero sin reducir el aislamiento.

## 2026-09-25 · PWA privada con HTTPS de Tailscale

- Contexto: iOS necesita un origen HTTPS para registrar el service worker y ejecutar ASTRO como una PWA real, pero el núcleo no debe hacerse público.
- Decisión: Publicar la app mediante Tailscale Serve en `https://astro-vps.tailbee6db.ts.net/`, con proxy a `127.0.0.1:8000`, y no usar Tailscale Funnel. Cachear únicamente la carcasa estática de la PWA y mantener las conversaciones fuera del almacenamiento del navegador.
- Motivo: Obtener HTTPS válido, WebSocket seguro e instalación en la pantalla de inicio sin abrir el servicio a Internet ni guardar datos privados en el dispositivo.
- Consecuencia: El nombre técnico del certificado queda visible en los registros públicos de certificados, con autorización de Jhony, pero solo los dispositivos del tailnet pueden acceder. Tailscale debe estar conectado; una reconexión crea una sesión nueva hasta que exista memoria persistente.

## 2026-09-26 · Web Push privado con VAPID

- Contexto: ASTRO necesita avisar en el iPhone incluso cuando la PWA está cerrada, sin publicar el núcleo en Internet ni guardar conversaciones en servicios de notificación.
- Decisión: Usar Web Push estándar con claves VAPID propias, suscripción iniciada expresamente desde la PWA instalada y entrega mediante el service worker. La clave privada permanece fuera de Git y se monta como secreto de Docker.
- Motivo: iOS permite Web Push en aplicaciones añadidas a la pantalla de inicio y no requiere una cuenta de desarrollador de Apple. El mecanismo mantiene ASTRO dentro del tailnet mientras el servicio Push entrega únicamente el aviso visible.
- Consecuencia: Cada dispositivo debe autorizar las notificaciones manualmente. El servidor conserva solo los datos técnicos de las suscripciones, elimina las expiradas y nunca incluye conversaciones en ellas. La primera prueba entregó correctamente un aviso al iPhone con ASTRO cerrado.

## 2026-09-26 · Selección manual de proveedor y modelo

- Contexto: Jhony quiere poder cambiar tanto el modelo como el proveedor de IA sin modificar Python y conservar OpenAI como opción principal.
- Decisión: Definir los proveedores compatibles en `config/config.yaml`, guardar cada clave en una variable distinta de `.env` y crear el cliente mediante una fábrica común. Configurar OpenAI como predeterminado y OpenRouter como alternativa seleccionable con `proveedor` y `modelo`.
- Motivo: Desacoplar el núcleo del servicio elegido y permitir pruebas o cambios operativos mediante configuración.
- Consecuencia: ASTRO nunca cambia de proveedor automáticamente ni duplica peticiones. Tras modificar el YAML hay que reiniciar el servicio. El registro de uso y el panel identifican el proveedor activo; al usar OpenRouter, las conversaciones pasan por OpenRouter y por el proveedor que sirve el modelo.

## 2026-09-27 · Enrutamiento seguro entre proveedores

- Contexto: El selector por YAML cumplía el cambio sin código, pero Jhony necesita controlarlo desde la PWA y mantener ASTRO disponible si el proveedor principal falla.
- Decisión: Mantener un principal y un respaldo configurables, persistir la selección fuera de Git y usar un circuit breaker de 120 segundos. El respaldo recibe el historial propio de ASTRO, el texto parcial visible y los resultados de herramientas completadas; el principal solo recupera el servicio al comenzar un turno posterior y superar una petición real.
- Motivo: Conservar continuidad y disponibilidad sin fingir que dos modelos comparten estado interno ni duplicar herramientas.
- Consecuencia: La continuación después de un corte puede reformular o repetir una pequeña parte, aunque ASTRO le pide que continúe desde el fragmento recibido. Las herramientas terminadas no se ejecutan de nuevo por un fallo posterior del proveedor. Las acciones externas de riesgo requerirán idempotencia y confirmación en sus fases correspondientes.

## 2026-09-27 · Fallo de preparación aislado por proveedor

- Contexto: Una clave ausente en el proveedor de respaldo cerró el WebSocket antes de que el proveedor principal pudiera responder.
- Decisión: Preparar cada ruta de forma independiente. Una ruta con clave o configuración ausente se marca como fallida y se omite; otra ruta disponible continúa el turno. Si ninguna puede prepararse, se genera un error controlado.
- Motivo: La degradación de un proveedor no debe destruir la conversación ni impedir usar otro proveedor sano.
- Consecuencia: El WebSocket permanece abierto y el historial se conserva ante este tipo de fallo de configuración.

## 2026-09-27 · Edición transaccional del historial

- Contexto: Corregir un mensaje antiguo cambia el contexto del que dependen todas las respuestas posteriores.
- Decisión: Identificar los turnos de cada WebSocket y, al editar, reconstruir el historial hasta el turno anterior. La nueva respuesta se genera antes de confirmar el rebobinado visual; si falla, se restaura el historial original.
- Motivo: Evitar conversaciones con dos versiones contradictorias y no perder mensajes ante un fallo de la API.
- Consecuencia: Guardar una edición elimina la respuesta antigua y todos los turnos posteriores. Cancelar o sufrir un error no altera la conversación. El uso ya consumido continúa en el contador.

## 2026-09-27 · Captura de voz local y separada del cerebro

- Contexto: El cerebro de ASTRO vive en el VPS, pero el VPS no puede oír el entorno físico de Jhony; el audio debe capturarse en el portátil y, más adelante, en los nodos locales de casa.
- Decisión: Capturar con `sounddevice` mediante `RawInputStream`, guardar WAV mono PCM de 16 bits a la frecuencia nativa del micrófono y mantener la dependencia en `requirements-voice.txt`. Las grabaciones se guardan bajo `data/audio`, fuera de Git.
- Motivo: Obtener un formato estándar compatible con la futura transcripción, sin necesitar NumPy ni instalar controladores de audio en el VPS.
- Consecuencia: Cada nodo de voz instalará sus dependencias locales y elegirá una entrada disponible. En el portátil de Jhony, WASAPI capturó correctamente a 48 kHz; los índices pueden cambiar al conectar dispositivos.

## 2026-09-27 · Transcripción local en CPU

- Contexto: ASTRO necesita convertir la voz capturada por sus nodos locales en texto español sin enviar audio privado al VPS ni a un proveedor externo.
- Decisión: Usar `faster-whisper==1.2.1` con el modelo multilingüe `base`, idioma español fijado, búsqueda de 5 haces, CPU y cuantización `int8`. El modelo se guarda bajo `data/models/faster-whisper`, fuera de Git.
- Motivo: El modelo base ofrece una primera transcripción correcta con una descarga de unos 148 MB, funciona en el portátil sin CUDA y procesa localmente el audio. La CPU permite completar esta fase sin instalar controladores adicionales.
- Consecuencia: La primera ejecución descarga el modelo y las siguientes pueden reutilizarlo localmente. La detección automática del final de la voz se mantiene para la fase 27 y la optimización con GPU, si resulta necesaria, para la fase 36.

## 2026-09-28 · Piper como voz local provisional

- Contexto: ASTRO necesita hablar sin internet y sin consumir una API. El Piper original dejó de mantenerse y el desarrollo actual continúa en `OHF-Voice/piper1-gpl` con licencia GPL-3.0-or-later.
- Decisión: Usar `piper-tts==1.8.0` como motor local y `es_ES-sharvard-medium`, hablante masculino `M` con identificador 0, como voz provisional. El modelo y los WAV se guardan bajo `data`, fuera de Git. La salida es mono PCM de 16 bits a 22.050 Hz.
- Motivo: La voz funciona completamente en local, genera audio más rápido que su duración y permite elegir explícitamente un hablante masculino de español de España.
- Consecuencia: Piper puede usarse en el ASTRO privado actual. Antes de distribuir ASTRO o extraer el módulo del restaurante como producto habrá que revisar y cumplir la GPL, o aislar o sustituir el motor. La voz definitiva y el respaldo automático con ElevenLabs se decidirán en la fase 35.

## 2026-09-28 · Conversación de voz manual de extremo a extremo

- Contexto: Las fases 23 a 25 probaron por separado la captura, la transcripción y la síntesis; faltaba unirlas con el núcleo remoto sin perder el historial.
- Decisión: Mantener un único WebSocket por conversación y ejecutar captura, Whisper y Piper en el nodo local. Enter inicia una grabación fija de seis segundos; solo la transcripción y la respuesta textual atraviesan la conexión privada con el VPS.
- Motivo: Reutilizar componentes probados, conservar una sesión coherente y evitar enviar grabaciones privadas al servidor o a proveedores externos.
- Consecuencia: Ya funciona el primer diálogo hablado completo. La duración fija puede cortar una frase o esperar de más, por lo que será sustituida por detección de fin de voz en la fase 27.

## 2026-09-28 · Detección local del final del habla

- Contexto: La conversación de voz esperaba siempre seis segundos, aunque Jhony hubiese terminado antes, y podía cortar intervenciones más largas.
- Decisión: Detectar voz localmente mediante RMS adaptado al ruido previo, bloques PCM16 de 30 ms y una ventana de activación. Conservar 0,3 segundos anteriores al inicio y cerrar después de 1 segundo continuo de silencio, con límites configurables de espera y duración.
- Motivo: El audio ya está disponible como PCM16 y puede analizarse sin otra dependencia, sin enviar grabaciones privadas y sin imponer una duración fija.
- Consecuencia: Las frases cortas terminan pronto y las pausas naturales inferiores a un segundo se conservan. Los entornos ruidosos necesitarán pruebas más amplias en la fase 38 y podrán motivar un detector neuronal si la medición demuestra que hace falta.

## 2026-09-28 · Streaming de voz y aceptación provisional de latencia

- Contexto: La voz se sintetiza y reproduce por fragmentos mientras llega la respuesta. La prueba real mostró seis fragmentos y 4,17 s indicados hasta la primera voz, frente a 4,34 s en la prueba anterior.
- Decisión: Jhony acepta cerrar la fase 28 con este funcionamiento y aplazar la optimización a la fase 36. Se conserva el modelo elegido y se configura `razonamiento: low`.
- Motivo: Jhony considera suficiente la respuesta actual y prefiere perfeccionarla más adelante.
- Consecuencia: El objetivo original de menos de tres segundos no se declara superado. Los 4,17 s se cuentan desde el final de la captura hasta antes de llamar al reproductor, excluyendo el silencio final del detector y la latencia del dispositivo. La fase 36 deberá medir desde el final real del habla hasta el inicio audible, además de desglosar transcripción, modelo y síntesis.

## 2026-09-28 · Acceso por dispositivo y privilegio mínimo

- Contexto: Tailscale limita la red, pero no identifica a la aplicación ni impide que una página abierta en un dispositivo del tailnet intente usar el WebSocket.
- Decisión: Exigir tokens aleatorios distintos por dispositivo, validar el origen web y aplicar límites de tamaño, frecuencia y conexiones. La PWA cambia el token una sola vez por una cookie segura; los clientes locales usan Bearer. Solo los dispositivos administradores pueden cambiar la IA o enviar una notificación de prueba.
- Motivo: Autenticar dentro de ASTRO, reducir el efecto de una credencial comprometida y cerrar HTTP y WebSocket con la misma política.
- Consecuencia: Cada dispositivo debe vincularse. Revocarlo requiere retirar o rotar su token privado en `.env.acceso` y reiniciar el servicio. La carcasa estática y `/health` siguen accesibles dentro del tailnet, pero no exponen conversación ni ajustes.

## 2026-09-28 · Procedencia estructurada del contexto

- Contexto: Las antiguas etiquetas `[Contexto interno de ASTRO: ...]` vivían como texto dentro del historial y un usuario podía escribir una etiqueta idéntica.
- Decisión: Guardar por separado el contenido conversacional y los nombres de herramientas ejecutadas. Solo el núcleo construye esos metadatos al preparar las instrucciones; ninguna etiqueta escrita en un mensaje cambia su autoridad.
- Motivo: La confianza debe depender de quién creó el dato y no de una cadena reconocible.
- Consecuencia: El historial visible queda limpio. Los futuros correos, páginas y sensores deberán entrar como datos no fiables con procedencia conservada, nunca como instrucciones por estar envueltos en una etiqueta.

## 2026-09-28 · Conversación por usuario y cancelación confirmada

- Contexto: Una reconexión creaba otra sesión y el servidor no podía leer `cancel` mientras esperaba al modelo.
- Decisión: Separar conversación y socket mediante una identidad por usuario autenticado, permitir un solo turno simultáneo y ejecutar la generación en una tarea cancelable. Los clientes confirman cuántos caracteres han visto u oído; al cancelar se conserva únicamente ese prefijo.
- Motivo: Dar continuidad entre voz y PWA y preparar la interrupción natural sin fingir que se oyó una respuesta completa.
- Consecuencia: Las reconexiones y dispositivos de Jhony comparten conversación mientras el proceso vive. Reiniciar el VPS aún borra el historial. Cerrar el stream es cooperativo y una herramienta ya terminada no se revierte; las futuras acciones externas necesitarán idempotencia y confirmaciones propias.

## 2026-09-28 · Respaldo independiente evaluado, no activado

- Contexto: OpenRouter usando un modelo de OpenAI protege frente a fallos de ruta, clave o límite, pero conserva una dependencia común del generador.
- Decisión: Mantener la configuración actual y registrar `google/gemini-3.8-flash` como candidato. La prueba sintética real mediante Responses API usó `calcular`, incorporó su resultado y respondió correctamente; no se modificó el proveedor activo ni el modelo de respaldo.
- Motivo: Comprobar compatibilidad técnica antes de decidir si las conversaciones pueden enviarse a otra empresa.
- Consecuencia: ASTRO continúa con OpenAI como principal y OpenRouter con el modelo actual como respaldo. Activar Gemini requerirá una decisión posterior de Jhony y aceptar que Google procese los mensajes enviados durante el respaldo.

## 2026-09-29 · Vinculación temporal con privilegio mínimo

- Contexto: Copiar una clave larga en cada navegador es incómodo y aumenta el riesgo de errores o exposición.
- Decisión: Un administrador puede emitir desde la PWA una vinculación de un solo uso, presentada como QR y código de ocho cifras. Caduca en cinco minutos; al reclamarla se crea un token aleatorio distinto y solo se guarda su huella SHA-256. Los dispositivos así añadidos pertenecen a Jhony, pero no son administradores.
- Motivo: Facilitar el alta sin convertir el QR o el código breve en una credencial permanente y sin repartir privilegios innecesarios.
- Consecuencia: Compartir el QR o código durante su vigencia permite vincular un dispositivo normal. La revocación individual y la gestión de permisos se añadirán en una fase posterior; mientras tanto permanece la vía de recuperación con clave larga.

## 2026-09-29 · Identidad y poder separados por dispositivo

- Contexto: Marcar un dispositivo como no administrador no impedía que compartiese la conversación de `jhony`.
- Decisión: Definir administrador, personal y restringido. Los dos primeros usan la identidad de Jhony; el tercero recibe identidad, historial, personalidad y herramientas aislados. Un administrador puede cambiar o revocar otros dispositivos, nunca el que está usando. Esta decisión sustituye la regla provisional de 28b por la que toda vinculación creaba un dispositivo sin administración.
- Motivo: Permitir distintos niveles de confianza sin convertir ASTRO en una plataforma multiusuario ni exponer información privada en equipos compartidos.
- Consecuencia: Promover a personal o administrador concede acceso al contexto de Jhony; cambiar a restringido cierra la conexión existente y obliga a iniciar una sesión aislada. Las nuevas herramientas no estarán disponibles para restringidos salvo autorización explícita.

## 2026-09-29 · Modelo propio de «Astro» entrenado en local

- Contexto: openWakeWord solo genera voces de entrenamiento en inglés, su cuaderno oficial exige Linux y descargas de unos 20 GB, y el modelo genérico «hey jarvis» no reconoce «Astro». Un primer modelo entrenado solo con voces sintéticas en español memorizaba: reconocía el 100 % en entrenamiento y el 45–65 % en validación, con 127–375 falsas activaciones por hora de habla continua.
- Decisión: Entrenar en el portátil, sin Colab, un clasificador pequeño (red densa de 64 neuronas) sobre las huellas de `melspectrogram` y `embedding_model` de openWakeWord. Datos: 70 grabaciones de Jhony (41 útiles), 9 voces españolas de Piper, 344 hablantes de LibriTTS-R, MLS alemán y L2-ARCTIC (con peso 0,5, por pronunciar «Astro» a su manera), aumento con ruido, reverberación, cambios de velocidad y tono y volumen de -34 a +3 dB, y habla real española de OpenSLR (corpus puertorriqueño y argentino masculino, CC BY-SA 4.0) como negativas. Se aplica minado de negativas difíciles en tres rondas. El modelo se guarda como `.npz` y se ejecuta solo con numpy; el filtro de voz es Silero VAD en ONNX, sin `torch`. El detector cuenta una activación si hubo voz en el último segundo, exige 3 bloques seguidos por encima de 0,8 y descansa 2 s. Tras comprobar en la práctica que se activaba con «astronauta» o «castro», se añadieron 61 grabaciones de Jhony y 1.143 clips sintéticos de palabras y frases con «astro» dentro, que entran siempre en el entrenamiento, y se pasó de 2 a 3 bloques seguidos.
- Motivo: Con pocos datos propios, la variedad de hablantes y de habla real como negativa es lo que más reduce la memorización y las falsas activaciones. Ejecutar sin `torch` mantiene el cliente ligero y compatible con Python 3.14.
- Consecuencia: En validación con audio que no se usó para entrenar, el detector completo activó 0 veces en 25 minutos de habla ajena real, 2 veces en 311 s de palabras parecidas reservadas (10 antes de añadir las negativas extra) y detectó 6 de las 11 grabaciones reservadas de Jhony; dos de las cinco fallidas son silencio casi total y otra probablemente no contiene «Astro». Las palabras parecidas no desaparecen del todo: «astronauta» o «castro» pueden activarlo de vez en cuando. Son cifras con muy poca muestra: el criterio de la fase se decide con las pruebas físicas. Un micrófono distinto o un volumen de entrada muy diferente exigen volver a grabar muestras y reentrenar. Los datos derivados de corpus CC BY-SA no deben distribuirse sin revisar la licencia; el modelo, las grabaciones y los corpus viven en `data/`, fuera de Git.

## 2026-09-29 · Estados de voz y progreso de herramientas

- Contexto: El cliente podía imprimir mensajes aproximados, pero no conocía cuándo el núcleo ejecutaba realmente una herramienta. Los cinco estados de la fase 30 necesitaban una fuente fiable y no una animación basada en tiempos.
- Decisión: Mantener la máquina de estados y sus señales sonoras en el nodo de voz. El núcleo emite por WebSocket `executing` justo antes de invocar una herramienta y `thinking` después de obtener su resultado. El evento contiene como máximo el nombre registrado de la herramienta; nunca incluye argumentos, resultados ni contenido privado.
- Consecuencia: El indicador refleja trabajo real y sirve de base para las fases de conversación continua e interrupción. Las señales son breves, se pueden desactivar con `--sin-sonidos-estado` y un fallo del altavoz conserva el indicador visual. Los clientes que no reconozcan el nuevo evento pueden ignorarlo sin romper el protocolo 2.

## 2026-09-29 · Ventana local de seguimiento

- Contexto: Exigir «Astro» delante de cada frase impide una conversación natural, pero dejar el micrófono abierto indefinidamente aumenta falsas capturas y gasto.
- Decisión: Después de una activación, el cliente local permite cinco intervenciones adicionales y espera un máximo de ocho segundos para que comience cada una. La primera frase activada no consume ese cupo. Solo una frase transcrita consume un seguimiento; el silencio termina la ventana y una transcripción fallida permite reintentar.
- Consecuencia: Los seis turnos comparten el mismo WebSocket y el mismo historial del núcleo sin cambios en el VPS. Tras el quinto seguimiento, una cancelación o inactividad, ASTRO vuelve a dormido. `--turnos-seguimiento` y `--espera-seguimiento` permiten ajustar los límites sin tocar código.

## 2026-09-29 · Destinatario conservador en seguimientos de voz

- Contexto: Durante la ventana continua, el micrófono puede capturar una frase dirigida a otra persona. La primera grabación, en cambio, comienza después de que el detector ya haya oído «Astro».
- Decisión: Aceptar directamente la primera frase activada y clasificar solo los seguimientos mediante salida JSON estructurada. Usar la última respuesta de ASTRO como contexto, tratar toda transcripción como dato no fiable y descartar frases ajenas, ambientales o dudosas. El descarte cierra la ventana y solo registra metadatos.
- Motivo: Evitar respuestas a conversaciones ajenas sin rechazar órdenes legítimas cuya palabra de activación ya no forma parte del audio transcrito.
- Consecuencia: Cada seguimiento hablado añade una petición pequeña al modelo. Ante duda o fallo, ASTRO calla y duerme; la frase no entra en el historial. La calidad depende de Whisper y se medirá con el conjunto de la fase 38.

## 2026-09-29 · Interrupción local con confirmación conservadora

- Contexto: Cancelar el stream remoto no basta para callar un audio que ya se está reproduciendo, y escuchar antes de que empiece la voz puede confundir ruido con una interrupción.
- Decisión: Escuchar con Silero VAD únicamente mientras ASTRO habla, exigir tres bloques de 32 ms y cortar el flujo de salida local en bloques de 20 ms. Enviar después `cancel` al núcleo y conservar como oído solo cada fragmento completado.
- Motivo: El corte audible debe ser inmediato e independiente de la latencia de red. Confirmar únicamente fragmentos completos evita guardar como escuchado contenido que quizá no llegó a oírse entero.
- Consecuencia: La prueba real cortó en 96 ms y el historial guardó solo «Claro, Jhony.». Hasta la cancelación de eco de la fase 34, la función sigue siendo opcional y requiere auriculares. Cancelar no revierte herramientas ya ejecutadas.

## 2026-09-29 · Cancelación de eco local con flujo dúplex

- Contexto: Escuchar el micrófono y reproducir la voz mediante flujos separados desalineaba la referencia acústica. ASTRO acababa confundiendo el eco de sus altavoces con la voz de Jhony.
- Decisión: Capturar y reproducir mediante un único flujo PortAudio dúplex a 16 kHz, en bloques de 10 ms. Cada bloque reproducido se entrega directamente a WebRTC AEC3 como referencia y solo la señal limpia pasa a Silero VAD. La integración nativa queda aislada detrás de código propio.
- Motivo: La cancelación necesita conocer exactamente qué audio salía cuando se capturó cada bloque. Subir el umbral del detector no corrige un desfase temporal.
- Consecuencia: ASTRO puede escuchar mientras habla usando altavoces, sin enviar audio fuera del equipo. La prueba real no produjo autoactivaciones y conservó una interrupción de 216 ms. Un cambio importante de micrófono, altavoz o disposición física deberá probarse otra vez.

## 2026-09-30 · ElevenLabs como voz principal y Piper como respaldo

- Contexto: Piper permite hablar sin Internet, pero su voz provisional no tiene la naturalidad buscada para ASTRO. Una voz en la nube introduce coste, latencia y dependencia externa.
- Decisión: Usar la voz original `ASTRO`, diseñada sin clonar personas reales, mediante Eleven v4 con estabilidad 1,0 y similitud 0,84. El cerebro genera para cada frase una dirección vocal privada y de vocabulario abierto; el núcleo la separa del texto visible y del historial, y el cliente la valida antes de sintetizar. Mantener Piper cargado localmente y cambiar automáticamente a él ante cualquier fallo de red, credencial, límite o servicio. La clave solo tiene permiso de texto a voz, un límite de 10.000 créditos por ciclo y vive en `.env`.
- Motivo: Jhony prioriza una voz natural, capaz de expresar cualquier emoción y combinación de matices, frente al menor coste y latencia de Flash. Piper evita que ASTRO se quede mudo cuando la nube no está disponible.
- Consecuencia: El texto que ASTRO pronuncia y su dirección vocal se envían a ElevenLabs durante el funcionamiento normal; Piper recibe únicamente texto limpio. Las marcas privadas no aparecen en la PWA ni en el historial, y las etiquetas externas se neutralizan. Los audios permanecen en `data/` y el registro solo conserva metadatos y número de caracteres. V4 consume más créditos que Flash; el contador real determinará cuándo hace falta un plan de pago.

## 2026-09-30 · ASTRO de escritorio: ventana sobre la PWA con puente local de voz

- Contexto: Hoy el estado de la voz solo se ve por colores en la terminal y el cliente de voz se lanza a mano. Jhony necesita ver cuándo ASTRO escucha y quiere una aplicación completa en el PC, equivalente a la PWA del iPhone y que además hable y oiga.
- Decisión: Crear el bloque 2b (fases 38a–38k), en paralelo al bloque 2 y en la rama `gui`. La aplicación de escritorio será una ventana que carga la PWA del VPS por Tailscale, para mantener una sola interfaz. La voz seguirá en un proceso local independiente que publica sus eventos por un WebSocket en 127.0.0.1, y la aplicación lo lanza y supervisa. La tecnología concreta (PySide6 o pywebview) se decide en la fase 38a tras verificar Python 3.14 y la conexión HTTPS a puerto local.
- Motivo: Reescribir en nativo el chat, la edición, el panel de Estado y la administración de dispositivos duplicaría la PWA. Separar procesos evita que un fallo de la ventana interrumpa la voz. Nada de audio sale del equipo.
- Consecuencia: La fase 37 queda cubierta en gran parte por 38d y 38j. Cada cambio de la PWA exige subir la versión de la caché para no romper el iPhone. Se relaja a propósito la regla de una fase cada vez: fase 36 en `main` y 38a en `gui`.

## 2026-09-30 · PySide6 para la aplicación de escritorio

- Contexto: La fase 38a comparó pywebview (WebView2) y PySide6 (Qt WebEngine). Ambos cargan la PWA, conservan la sesión y permiten el puente local, la bandeja y el atajo global. Solo Qt logró un orbe flotante translúcido; pywebview dejó siempre un rectángulo con tres métodos distintos.
- Decisión: Usar PySide6 6.11.2 (Essentials y Addons) para la ventana de ASTRO: un motor web que carga la PWA con perfil persistente y un orbe dibujado nativamente. El cierre de la ventana la oculta en la bandeja.
- Motivo: El indicador visual siempre presente es el objetivo del bloque 2b y solo Qt lo cumple de forma limpia. El coste, unos 500 MB instalados y unos 370 MB en ejecución con la PWA, es aceptable.
- Consecuencia: El puente local en 127.0.0.1 debe comprobar el Origin y exigir un token, porque el navegador permite que cualquier página conecte a él. La GUI sigue siendo un proceso aparte de la voz. Como el proceso de la GUI es independiente, su versión de Python puede diferir de la del resto si hiciera falta.

## 2026-09-30 · Identidad del PC en el almacén de credenciales de Windows

- Contexto: La aplicación de escritorio necesita una identidad propia y revocable. La cookie del perfil web caduca a los 30 días, aunque el token del servidor no caduca, y un token en `.env` queda en claro.
- Decisión: Vincular el PC con el código de un solo uso de la fase 28b, guardar el token en el almacén de credenciales de Windows (`keyring`) y reinyectarlo como cookie en cada arranque. Solo una respuesta 401 del servidor borra el token y devuelve la app a la pantalla de vincular; un fallo de red nunca lo hace.
- Motivo: Separa la identidad del perfil del navegador, evita la caducidad de 30 días, permite revocar desde «Estado» sin cambiar el servidor y no deja el token en un archivo de texto.
- Consecuencia: Sin cambios ni despliegue en el VPS. Cualquier proceso del usuario de Windows puede leer el token del almacén, igual que antes con `.env`. El cliente de voz seguirá con `ASTRO_DEVICE_TOKEN` hasta que la fase 38d unifique ambas identidades. Cerrar la ventana cierra la app hasta que exista la bandeja (38e).

## 2026-10-01 · Puente local opt-in con el cliente de voz como servidor

- Contexto: La ventana de escritorio necesita conocer en tiempo real qué hace la voz, sin que un fallo de la ventana afecte a la conversación. El navegador permite que cualquier página conecte con 127.0.0.1.
- Decisión: El cliente de voz publica sus eventos por un WebSocket en 127.0.0.1, con puerto asignado por el sistema y token aleatorio nuevo en cada arranque guardado en `data/puente.json`. Se comprueban `Origin` y `Host`, el primer mensaje debe autenticarse en 3 s y hay un máximo de 4 clientes. El puente solo arranca con `--puente`. El protocolo lleva versión e incluye `hello`, `state` y `transcript`; la transcripción se publica solo si la frase iba dirigida a ASTRO.
- Motivo: Que la voz sea el servidor permite que funcione sola y que la ventana se conecte cuando quiera. Publicar sin esperar y descartar a los receptores lentos garantiza que nada del lado de la ventana pueda frenar o romper la voz. Desactivarlo por defecto no cambia el comportamiento de lo ya validado.
- Consecuencia: Se añadieron cambios mínimos y solo de adición en `voice/estados.py` y `clients/voz.py`. Matar el cliente a la fuerza deja un `data/puente.json` antiguo, que los receptores toleran reintentando. El nivel del micrófono y la voz activa se publicarán en las fases 38e y 38h. La fase 38d deberá lanzar el cliente con `--puente`.

## 2026-10-01 · Ruta de voz de baja latencia

- Contexto: La cadena anterior esperaba la transcripción completa, la respuesta del núcleo y suficiente texto para sintetizar, provocando entre 10 y 15 segundos hasta la primera palabra.
- Decisión: Usar OpenAI Realtime para la conversación rápida y conservar ElevenLabs v4 Turbo como voz audible mediante síntesis continua en streaming. Piper continúa como respaldo. El reproductor dúplex mantiene un búfer inicial de 200 ms y actualiza el retardo real de PortAudio para la cancelación de eco.
- Motivo: Mantener la voz expresiva elegida por Jhony y conseguir conversación fluida sin perder la interrupción local.
- Consecuencia: El audio de esta ruta se envía a OpenAI y el texto generado se envía a ElevenLabs. Si falla ElevenLabs, ASTRO avisa y cambia a Piper. La naturalidad del contenido seguirá ajustándose sin reabrir la optimización de latencia.

## 2026-10-01 · Conversación canónica y reorganización del escritorio

- Contexto: La revisión del bloque 2b encontró que la ruta Realtime seguía siendo una prueba directa sin herramientas ni historial central, 38c prometía eventos aplazados y las fases 37, 38d y 38j se solapaban. También se afirmaba que ningún audio salía del equipo aunque la ruta rápida lo envía a OpenAI.
- Decisión: El núcleo será la fuente canónica de todos los turnos. Antes de crear el supervisor, la fase 38d integrará la ruta Realtime con el historial, las herramientas y el respaldo clásico. Las fases posteriores avanzan una letra hasta 38l. El supervisor será independiente de la ventana, y Windows iniciará ASTRO al entrar Jhony en su sesión, no como un servicio de sesión 0.
- Motivo: Evitar dos ASTRO con contextos diferentes, impedir turnos duplicados en la PWA y conservar micrófono, altavoz y credenciales dentro de la sesión interactiva de Windows.
- Consecuencia: La privacidad documenta por separado la ruta clásica local y la ruta Realtime que envía audio cifrado a OpenAI. La fase 37 se convierte en un objetivo coordinado y se cerrará con 38k. Cada fase conserva sus propias pruebas y 38l queda reservada para integración y resistencia.

## 2026-10-01 · Una sola ruta de voz de producción

- Contexto: La prueba Realtime directa de la fase 36 logró menos de dos segundos, pero mantenía una conversación distinta, sin herramientas ni historial compartido. Se probó como alternativa usar Realtime solo para transcribir y enviar después el texto al núcleo; funcionó, pero la transcripción tardó 4,06 s antes de que el núcleo pudiera empezar.
- Decisión: La ruta de producción será única: Whisper local transcribe, el núcleo canónico selecciona Luna o Astra y ejecuta herramientas, y ElevenLabs habla con Piper como respaldo. Se eliminan del cliente los modos Realtime para que no puedan crear otro historial ni activarse por accidente.
- Motivo: Una conversación coherente, las herramientas y la continuidad entre dispositivos pesan más que una medición rápida obtenida saltándose el cerebro de ASTRO. El núcleo con Luna produjo su primer texto en 0,753 s, por lo que la ruta completa puede mantener el objetivo de latencia sin duplicar la arquitectura.
- Consecuencia: El audio capturado permanece local. PWA y voz comparten la conversación por usuario autenticado y el respaldo de proveedor ocurre dentro del mismo turno del núcleo. Los módulos de medición Realtime pueden conservarse como referencia de la fase 36, pero no forman parte del cliente de producción.

## 2026-10-01 · Supervisor independiente y tres bloqueos de instancia

- Contexto: Si la GUI fuera propietaria del cliente de voz, cerrar o bloquear la ventana silenciaría ASTRO. Además, abrir dos veces la aplicación podía duplicar ventana, micrófono y puente.
- Decisión: Separar ventana, supervisor y voz en procesos distintos. Cada nivel mantiene un bloqueo exclusivo liberado por el sistema operativo. El supervisor reinicia errores tras 1, 2 y 4 segundos, se detiene después de tres reinicios rápidos y reinicia el contador cuando la voz permanece estable cinco minutos.
- Motivo: La PWA puede cerrarse o fallar sin afectar la escucha, y ningún archivo PID obsoleto puede bloquear ASTRO permanentemente.
- Consecuencia: Cerrar la ventana ya no detiene la voz. Una salida normal no se reinicia. El estado y los PID se publican sin datos privados en `data/gui/supervisor.json`; los registros quedan fuera de Git. El apagado desde la bandeja se añadirá cuando exista ese control.
