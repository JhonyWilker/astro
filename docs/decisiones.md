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
