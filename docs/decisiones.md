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
