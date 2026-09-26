# Log de ASTRO

Una entrada por fase cerrada, la más reciente al final.

Formato:

```
## AAAA-MM-DD · Fase N — Nombre de la fase
- Hecho:
- Falló:
- Decidido:
- Siguiente: fase N+1
```

---

## 2026-09-24 · Fase 1 — Definir ASTRO 0.1 en una página
- Hecho: Se definieron el propósito, las capacidades, los límites, la personalidad, la privacidad, el presupuesto y los criterios de éxito de ASTRO 0.1 en `docs/vision.md`.
- Falló: Se detectó una contradicción entre el plan, que mencionaba Claude, y la decisión de usar ChatGPT. No hubo fallos técnicos.
- Decidido: ASTRO 0.1 usará la API de ChatGPT, conversará por texto y voz sin memoria entre sesiones ni acciones externas, tendrá un límite de 50 € al mes y será la base de un asistente personal más amplio.
- Siguiente: fase 2 — Inventario de equipos y dispositivos.

## 2026-09-25 · Fase 2 — Inventario de equipos y dispositivos
- Hecho: Se documentaron el portátil principal, periféricos, dispositivos móviles, torre Dell, ordenador Linux, redes de casa y restaurante y dispositivos conectados en `docs/inventario.md`.
- Falló: Las primeras consultas de hardware fueron bloqueadas por el entorno protegido y se repitieron con permiso. Windows informó incorrectamente 4 GB de memoria gráfica; `nvidia-smi` confirmó 6 GB.
- Decidido: El HP Victus será el equipo principal de desarrollo; la Dell OptiPlex permanecerá en el restaurante como posible nodo local; el VPS se contratará en la fase 9a y no se adelantará ninguna compra.
- Siguiente: fase 3 — Instalar Python, VS Code y Git.

## 2026-09-25 · Fase 3 — Instalar Python, VS Code y Git
- Hecho: Se comprobaron Python 3.14.7, Git 2.53.0 para Windows y Visual Studio Code 1.109.3 de 64 bits. Las tres herramientas ya estaban instaladas y funcionan desde PowerShell.
- Falló: No hubo fallos. Se revisó la compatibilidad de Python 3.14 con las principales dependencias futuras de voz antes de decidir mantenerlo.
- Decidido: El desarrollo se hará en el portátil HP Victus con las versiones ya instaladas; no se instalará otra versión de Python mientras no aparezca una incompatibilidad real.
- Siguiente: fase 4 — Crear la cuenta de GitHub y el repositorio privado `astro`.

## 2026-09-25 · Fase 4 — Crear el repositorio privado en GitHub
- Hecho: Se configuró la identidad local de Git con el correo privado de GitHub, se creó `.gitignore`, se inició la rama `main`, se creó el primer commit y se subió al repositorio privado `JhonyWilker/astro`.
- Falló: GitHub CLI no estaba instalado, por lo que se creó el repositorio desde la web. El entorno aislado creó inicialmente `.git` con otro propietario; se corrigió la propiedad antes de continuar.
- Decidido: El código de ASTRO se guardará en un repositorio privado de GitHub, los commits usarán el correo privado de GitHub y la rama principal será `main`.
- Siguiente: fase 5 — Python I: variables, funciones, condiciones y bucles.

## 2026-09-25 · Fase 5 — Python I
- Hecho: Se resolvieron y ejecutaron cinco ejercicios sobre variables, operaciones, condiciones, bucles `for`, bucles `while` y funciones en `ejercicios/fase_05_python_i.py`.
- Falló: La primera ejecución mostró incorrectamente los símbolos `°` y `€` por la codificación de la consola. La ejecución con el modo UTF-8 mostró el resultado correcto.
- Decidido: Como Jhony ya conoce los fundamentos de Python, la fase se validó mediante una prueba rápida en lugar de repetir la teoría.
- Siguiente: fase 6 — Python II: listas, diccionarios, archivos y JSON.

## 2026-09-25 · Fase 6 — Python II
- Hecho: Se creó y ejecutó un programa que usa listas, diccionarios y archivos para guardar y recuperar una configuración de ASTRO en formato JSON.
- Falló: No hubo fallos; la comparación confirmó que los datos recuperados coinciden exactamente con los originales.
- Decidido: La fase se validó mediante una prueba práctica rápida. Los archivos JSON del proyecto usarán UTF-8 y formato indentado para que sean legibles.
- Siguiente: fase 7 — Entornos virtuales y paquetes.

## 2026-09-25 · Fase 7 — Entornos virtuales y paquetes
- Hecho: Se creó `.venv`, se instaló `python-dotenv` 1.2.3, se generó `requirements.txt` y se comprobó que permite instalar e importar la dependencia.
- Falló: El primer intento de descarga fue bloqueado por la red del entorno aislado. Se repitió con permiso y la instalación terminó correctamente.
- Decidido: Las dependencias de ASTRO se instalarán en `.venv`, se fijarán con versión exacta en `requirements.txt` y el entorno virtual nunca se subirá a Git.
- Siguiente: fase 8 — Cuenta y API de OpenAI, clave en `.env` y límite de gasto mensual.

## 2026-09-25 · Fase 8 — Cuenta y API de OpenAI
- Hecho: Se creó el proyecto independiente `ASTRO` en OpenAI, se configuró un límite duro mensual de 50 USD con alertas al 80 % y al 100 %, se guardó una clave restringida en `.env`, se instaló `openai` 3.19.2 y `ejercicios/fase_08_openai.py` imprimió `ASTRO conectado correctamente.`.
- Falló: Los dos primeros intentos devolvieron un error 401 porque el contenido copiado en `.env` quedó duplicado. Se detectó y corrigió sin mostrar la clave; la tercera ejecución funcionó.
- Decidido: ASTRO tendrá un proyecto separado en OpenAI, usará inicialmente `gpt-6-astra`, mantendrá la recarga automática desactivada y la clave sin caducidad, restringida a peticiones al modelo. La clave permanecerá solo en `.env` y nunca se subirá a GitHub.
- Siguiente: fase 9 — Crear la estructura de carpetas del proyecto.

## 2026-09-25 · Fase 9 — Crear la estructura de carpetas del proyecto
- Hecho: Se crearon y verificaron las carpetas `core`, `voice`, `memory`, `tools`, `proactive`, `clients`, `config` y `tests`. Cada una contiene un `README.md` que delimita su responsabilidad; `docs` ya existía.
- Falló: No hubo fallos técnicos. Como Git no conserva carpetas vacías, se usaron documentos breves en lugar de marcadores sin contenido.
- Decidido: La estructura seguirá el diseño modular del plan. No se añadirán paquetes Python ni código vacío hasta que una fase los necesite; `ejercicios` se conserva como material de aprendizaje.
- Siguiente: fase 9a — Crear el VPS en la UE: cortafuegos, Tailscale y copias automáticas.

## 2026-09-25 · Fase 9a — Crear el VPS en la UE
- Hecho: Se contrató un Hostinger KVM 2 con pago mensual y Ubuntu 26.04.1 LTS; se instaló Tailscale, se activó UFW con entrada exclusiva por `tailscale0` y se comprobó que el SSH privado funciona mientras el público expira. Se configuraron copias cifradas con restic y rclone en Google Drive, ejecución diaria a las 03:30, retención de 7 diarias, 4 semanales y 6 mensuales, y se validaron dos instantáneas, la integridad del repositorio y una restauración real.
- Falló: Hetzner exigió verificación de identidad y se cambió de proveedor. La primera clave privada quedó con propietario del entorno aislado y se creó una copia con permisos exclusivos para Jhony. PowerShell interpretó localmente una comprobación de limpieza; la restauración había funcionado y la carpeta temporal se verificó y eliminó por separado.
- Decidido: El VPS será Hostinger KVM 2 mensual, sin Monarx ni el administrador de Docker. Solo se accederá mediante Tailscale y clave SSH. Las copias diarias usarán Google Drive con permiso limitado `drive.file` y cifrado de restic; la copia semanal incluida de Hostinger queda como segunda capa. El límite de OpenAI de 50 USD se mantiene separado del coste del VPS.
- Siguiente: fase 10 — Crear `docs/log.md` y la rutina de sesión.

## 2026-09-25 · Fase 10 — Crear el diario y la rutina de sesión
- Hecho: Se formalizó la rutina de inicio, ejecución y cierre en `docs/rutina-sesion.md` y se enlazó desde `AGENTS.md`. Una prueba automática confirmó que existen el plan, el diario y la rutina, que el diario tiene entradas, que solo hay una fase actual y que las tres secciones de la rutina están presentes. La puerta del bloque 0 se validó con `ejercicios/puerta_bloque_0.py`: tiene exactamente 10 líneas, consulta la API y respondió `Puerta del bloque 0 superada.`.
- Falló: El plan pedía crear `docs/log.md`, pero ya existía y contenía las entradas de las fases anteriores; no se recreó ni se perdió historial. No hubo fallos técnicos.
- Decidido: Cada sesión seguirá la lista de `docs/rutina-sesion.md`. Una autorización expresa para toda una fase cubrirá sus comandos y archivos ordinarios dentro del repositorio; las acciones de mayor riesgo seguirán confirmándose en el momento correspondiente.
- Siguiente: fase 11 — Chat en terminal: pregunta → modelo → respuesta.

## 2026-09-25 · Fase 11 — Chat de un turno en la terminal
- Hecho: Se creó `core/chat.py`, que carga la configuración privada, pide una pregunta con `input()`, la envía a la API de ChatGPT y muestra la respuesta con el prefijo `ASTRO:`. Se documentó su uso en `core/README.md`. La compilación no mostró errores, la entrada vacía se rechazó sin llamar a la API y una pregunta real recibió una respuesta correcta de un turno.
- Falló: No hubo fallos técnicos.
- Decidido: El código separa la creación del cliente, la petición al modelo y la interfaz de terminal para poder ampliarlo en las siguientes fases. La fase 11 se limita deliberadamente a un intercambio; el historial se añadirá en la fase 12, la personalidad en la 13 y el manejo avanzado de errores en la 17.
- Siguiente: fase 12 — Historial: recuerda lo dicho en la misma conversación.

## 2026-09-25 · Fase 12 — Historial durante la conversación
- Hecho: Se amplió `core/chat.py` con un bucle de conversación y una lista de historial que conserva cada mensaje de Jhony y cada respuesta de ASTRO durante la ejecución. El comando `salir` termina el chat sin llamar a la API y `core/README.md` documenta el comportamiento. Una prueba real de 10 turnos confirmó que ASTRO recuerda el nombre Jhony, el proyecto ASTRO, una palabra y un número, acepta una corrección, usa el número en un cálculo y resume el estado actualizado.
- Falló: La primera captura de una salida local mostró incorrectamente una tilde por la codificación de PowerShell. Se ejecutó la prueba real con UTF-8 y todo el texto se mostró correctamente; no era un fallo del programa.
- Decidido: El historial se mantiene únicamente en memoria y se envía completo en cada turno. Al cerrar el programa desaparece; la persistencia entre sesiones se añadirá en el bloque 3.
- Siguiente: fase 13 — Personalidad de ASTRO.

## 2026-09-25 · Fase 13 — Personalidad de ASTRO
- Hecho: Se creó `config/personality.md` con la identidad, el trato, el idioma, el tono, el criterio y las reglas de privacidad de ASTRO. `core/chat.py` carga el archivo una vez al arrancar y lo envía separado del historial mediante `instructions`. Las pruebas locales confirmaron que el código compila y la configuración se carga; una conversación real de cinco turnos confirmó que ASTRO se identifica correctamente, llama Jhony a su usuario, explica con claridad, no presenta invenciones como hechos, protege conversaciones privadas y cambia de idioma cuando corresponde.
- Falló: El primer intento de la prueba real fue bloqueado por los permisos de red del entorno protegido con `WinError 10013`; se repitió con acceso autorizado y terminó correctamente. La captura de PowerShell mostró algunos caracteres acentuados con codificación incorrecta, sin afectar a los archivos UTF-8 ni a la respuesta recibida.
- Decidido: ASTRO tendrá identidad propia y una personalidad serena, inteligente, elegante, directa y discreta, con humor seco ocasional. Usará español de España por defecto, se dirigirá al usuario como «Jhony», hablará en masculino y no copiará la identidad, frases ni voz de JARVIS, FRIDAY, otros personajes o personas reales.
- Siguiente: fase 14 — Respuestas en streaming.

## 2026-09-25 · Fase 14 — Respuestas en streaming
- Hecho: Se modificó `core/chat.py` para solicitar respuestas con `stream=True`, procesar los eventos `response.output_text.delta` y mostrar cada fragmento inmediatamente con `flush=True`. Los fragmentos se acumulan y se unen al terminar para conservar la respuesta completa en el historial. La prueba local simuló tres fragmentos y confirmó su reconstrucción; la prueba real mostró una respuesta de 12 puntos en una terminal interactiva y un segundo turno recordó correctamente que eran 12.
- Falló: No hubo fallos técnicos. La herramienta que captura la terminal agrupó parte de la salida visual, pero el prefijo apareció antes de completarse la respuesta y las pruebas confirmaron que cada evento se imprime individualmente.
- Decidido: El chat usará el streaming de la Responses API mediante eventos semánticos. La interfaz muestra el texto conforme llega y el historial recibe la respuesta completa reconstruida; el manejo avanzado de interrupciones y errores seguirá en sus fases previstas.
- Siguiente: fase 15 — Configuración central.

## 2026-09-25 · Fase 15 — Configuración central
- Hecho: Se instaló PyYAML 6.0.3 y se creó `config/config.yaml` como fuente central del modelo, el idioma y los límites. `core/chat.py` carga y valida esos valores al arrancar, aplica el modelo y el máximo de tokens a la API, añade el idioma a las instrucciones y limita el contexto a los turnos configurados. Las pruebas locales confirmaron los valores reales, rechazaron un límite inválido y demostraron que `modelo-prueba`, otro idioma y otros límites llegan al cliente sin modificar Python. Una petición real confirmó que ASTRO arranca y reconoce el español de España como idioma habitual.
- Falló: No hubo fallos técnicos. La captura de PowerShell volvió a representar incorrectamente algunos caracteres acentuados, sin afectar a las comparaciones Unicode, los archivos UTF-8 ni la respuesta de la API.
- Decidido: La configuración inicial usa `gpt-6-astra`, español de España, un máximo de 2000 tokens de salida y 20 turnos de historial. `.env` queda reservado para secretos; cambiar valores operativos requiere editar `config/config.yaml` y reiniciar ASTRO, no modificar código.
- Siguiente: fase 16 — Registro de tokens, coste y tiempo de respuesta.

## 2026-09-25 · Fase 16 — Registro de tokens, coste y tiempo
- Hecho: Se creó `core/uso.py` para calcular, guardar y resumir el uso de cada petición. El chat captura el evento final `response.completed`, registra tokens de entrada, caché, salida, razonamiento y total, mide la duración con un reloj monotónico y calcula el coste estimado con tarifas configurables. Los metadatos se añaden a `logs/uso.jsonl`, ignorado por Git y sin contenido de conversaciones. Una prueba determinista validó un coste conocido de 0,01345 USD; una petición real registró 472 tokens, 5,05 segundos y 0,008600 USD, y el informe diario reprodujo esos totales.
- Falló: La primera inspección local usó un nombre de clase que el SDK no exporta y produjo `ImportError`; se revisaron los tipos instalados y se usaron los campos reales del evento. La captura de PowerShell mostró algunas tildes incorrectamente, sin afectar a los datos UTF-8.
- Decidido: El coste se expresa en USD y se considera una estimación; la factura de OpenAI es la referencia definitiva. Las tarifas estándar de `gpt-6-astra` quedan en `config/config.yaml`, con `service_tier=default`, y deberán actualizarse al cambiar de modelo o precio. Los registros de uso nunca guardarán preguntas ni respuestas.
- Siguiente: fase 17 — Manejo de errores, falta de conexión y reintentos.

## 2026-09-25 · Fase 17 — Manejo de errores y reintentos
- Hecho: Se configuraron en `config/config.yaml` un timeout de 30 segundos por intento y 2 reintentos automáticos del SDK. ASTRO distingue conexión, timeout, límites temporales y permanentes, autenticación, permisos, peticiones inválidas, fallos internos y streams incompletos; muestra un mensaje útil, elimina del historial la pregunta fallida y continúa abierto. `core/errores.py` guarda únicamente fecha, tipo, estado HTTP, código y recuperabilidad en `logs/errores.jsonl`. Las pruebas simuladas confirmaron todos los mensajes, la continuidad del bucle y la ausencia de reintentos tras una respuesta parcial; una petición real posterior respondió correctamente.
- Falló: La primera inspección de los tipos de uso en la sesión anterior asumió un nombre no exportado, pero en esta fase no hubo fallos de implementación ni de prueba. La captura de PowerShell volvió a mostrar algunas tildes incorrectamente sin afectar al UTF-8.
- Decidido: Los reintentos quedan a cargo del SDK para evitar bucles anidados: 2 reintentos y 30 segundos por intento. ASTRO no repite automáticamente una petición si el streaming ya comenzó. Los fallos que exigen intervención, como clave inválida o límite de gasto, no se clasifican como recuperables.
- Siguiente: fase 18 — Herramienta de fecha y hora.

## 2026-09-25 · Fase 18 — Primera herramienta: fecha y hora
- Hecho: Se creó `tools/fecha_hora.py` con un contrato estricto para la Responses API y una función local que devuelve fecha, hora, día de la semana, zona y desfase UTC. `core/chat.py` permite al modelo solicitarla, ejecuta la función con `Europe/Madrid` y envía el resultado a una segunda petición en streaming. La configuración valida la zona al arrancar y cada petición conserva su propio registro de uso. Una prueba determinista convirtió correctamente una fecha UTC a Madrid; una simulación validó el flujo completo y una prueba real respondió `Jhony, hoy es viernes, 25 de septiembre de 2026.`.
- Falló: Windows no incluía la base IANA que necesita `zoneinfo` y produjo `ZoneInfoNotFoundError`; se instaló y fijó `tzdata==2026.4` dentro del entorno virtual. La captura de PowerShell volvió a mostrar algunas tildes incorrectamente, sin afectar a los archivos UTF-8 ni a las comprobaciones.
- Decidido: La zona horaria se configura como `Europe/Madrid` y Python obtiene el dato real; el modelo solo decide cuándo usar la herramienta y redacta la respuesta. Un turno con herramienta registra sus dos peticiones. En esta fase se admite una única llamada de fecha y hora; el registro genérico y el encadenamiento llegarán en las fases 20 y 21.
- Siguiente: fase 19 — Segunda herramienta: calculadora.

## 2026-09-25 · Fase 19 — Segunda herramienta: calculadora
- Hecho: Se creó `tools/calculadora.py` con un contrato estricto para la Responses API y un evaluador aritmético basado en `ast`, `Fraction` y `Decimal`. Admite números, paréntesis, signos, suma, resta, multiplicación, división, división entera, resto y potencias acotadas; devuelve resultado exacto y representación decimal. `core/chat.py` ofrece al modelo fecha/hora y calculadora, ejecuta explícitamente la elegida y devuelve errores aritméticos seguros al modelo. Las pruebas locales validaron enteros grandes, decimales, fracciones y operadores; rechazaron código, nombres, listas, división por cero y exponentes excesivos. La simulación reprodujo el flujo completo y una prueba real calculó `(0.1 + 0.2) * 10` como `3`.
- Falló: No hubo fallos de implementación ni de prueba. La captura de PowerShell mostró algunas tildes incorrectamente, sin afectar al código UTF-8 ni a las aserciones.
- Decidido: Los cálculos nunca usarán `eval` ni se dejarán al cálculo mental del modelo. La calculadora acepta solo un subconjunto aritmético explícito, limita entrada, exponentes y tamaño de resultado y conserva fracciones exactas. Durante esta fase se mantiene una sola llamada de herramienta por turno.
- Siguiente: fase 20 — Registro genérico de herramientas.

## 2026-09-25 · Fase 20 — Registro genérico de herramientas
- Hecho: Se crearon `tools/base.py` y `tools/registro.py`. Cada herramienta declara en una ficha común su nombre, descripción, esquema de parámetros, riesgo y ejecutor. El registro descubre automáticamente los módulos de `tools`, rechaza nombres duplicados o archivos incompletos, genera los contratos para la API y ejecuta por nombre con una interfaz común. Fecha/hora y calculadora se adaptaron al formato con riesgo bajo, y `core/chat.py` dejó de importarlas o conocer sus nombres. Las pruebas confirmaron descubrimiento, metadatos, ejecución, errores controlados y ausencia de acoplamiento; una simulación validó el chat y una consulta real respondió la hora de Madrid.
- Falló: No hubo fallos de implementación ni de prueba. La captura de PowerShell mostró algunas tildes incorrectamente, sin afectar a los archivos UTF-8 ni a las comprobaciones.
- Decidido: Añadir una herramienta requiere un único archivo que exporte `HERRAMIENTA`; el núcleo y el registro no se editan. Los riesgos disponibles son bajo, medio y alto. Por ahora son metadatos; las reglas de autorización `AUTO`, `ASK` y `DENY` pertenecen a la fase 53.
- Siguiente: fase 21 — Bucle de agente.

## 2026-09-25 · Fase 21 — Bucle de agente
- Hecho: `core/chat.py` ahora mantiene dentro de cada turno una entrada de trabajo acumulada y alterna entre el modelo y el registro hasta recibir una respuesta sin nuevas llamadas. Conserva el texto y el uso de todas las peticiones y ejecuta las herramientas de una en una. Se añadió `agente.pasos_herramienta_maximos: 5` a la configuración y un error específico que detiene la tarea antes de superar el límite. Una simulación encadenó fecha, suma y multiplicación, produjo cuatro registros y validó la protección con límite 2. La prueba real resolvió sola tres pasos: obtuvo el año 2026, calculó 2036 y después 4072 mediante dos llamadas separadas a la calculadora.
- Falló: La primera inspección de la simulación conservó referencias a una lista mutable y no pudo distinguir los estados intermedios; se corrigió el cliente falso para copiar cada petición al recibirla. No era un fallo del bucle real. La captura de PowerShell representó incorrectamente algunas tildes y el signo de multiplicación, sin afectar a los datos ni a los resultados.
- Decidido: El agente ejecuta una herramienta cada vez y acumula todos los resultados del turno. El límite inicial es 5 ejecuciones, configurable entre 1 y 10; después de la última ejecución permitida puede realizar una petición final de redacción, pero no otra herramienta.
- Siguiente: fase 22 — Primeras pruebas automáticas del núcleo.

## 2026-09-25 · Fase 22 — Primeras pruebas automáticas del núcleo
- Hecho: Se instaló y fijó `pytest==9.1.1` y se crearon 10 pruebas en `tests/test_configuracion.py`, `tests/test_herramientas.py` y `tests/test_nucleo.py`. Cubren configuración válida e inválida, coste estimado, fecha/hora, exactitud y seguridad de la calculadora, descubrimiento y ejecución del registro, mensaje del límite y una cadena completa de tres herramientas con cuatro peticiones simuladas. Los dobles de prueba sustituyen la API y neutralizan los registros, por lo que la suite no usa internet, no consume saldo y no lee `.env`. `pytest --collect-only` encontró exactamente 10 pruebas y la ejecución terminó con `10 passed` en 0,72 segundos.
- Falló: No hubo fallos de implementación ni de prueba. Las cachés creadas por Python y pytest ya estaban cubiertas por `.gitignore` y no se incluirán en el repositorio.
- Decidido: La suite rápida será determinista, local y sin dependencias externas. Las integraciones reales se validarán por separado cuando corresponda; los errores corregidos deberán recibir una prueba de regresión para evitar que reaparezcan.
- Siguiente: fase 22a — Núcleo desplegado en el VPS con FastAPI + WebSocket.

## 2026-09-25 · Fase 22a — Núcleo desplegado en el VPS con FastAPI + WebSocket
- Hecho: Se separó el núcleo compartido de cada sesión, se creó una API FastAPI con salud, cliente web y conversación WebSocket en streaming, y se añadió un cliente de terminal que usa el mismo protocolo. Se instalaron Docker Engine 29.8.1 y Docker Compose 5.5.1 desde el repositorio oficial en el VPS, se desplegó ASTRO en `/opt/astro` y se protegió el contenedor con usuario sin privilegios, raíz de solo lectura, capacidades eliminadas y reinicio automático. El puerto 8000 quedó enlazado solo a `100.123.43.31`, la IP de Tailscale. Las 13 pruebas pasaron; el terminal calculó `125 × 48 = 6000` y el navegador respondió la hora de Madrid contra el mismo servicio. Un reinicio controlado devolvió el contenedor a estado saludable y `/health` siguió respondiendo desde el portátil.
- Falló: La primera prueba real local no pudo acceder a OpenAI dentro del entorno aislado y se repitió con red autorizada. El primer cliente remoto recibió `WinError 5` al intentar usar Tailscale desde el entorno protegido y funcionó con permiso. Una copia inicial incluyó cachés `__pycache__`, que se eliminaron del VPS; el primer comando de limpieza y el primer comando de reinicio fueron interpretados parcialmente por PowerShell y se repitieron con rutas y órdenes literales. La transferencia de `.env` fue bloqueada hasta recibir autorización explícita de Jhony. Ninguno de estos fallos dejó el servicio expuesto ni secretos en Git.
- Decidido: FastAPI y WebSocket serán la única entrada del núcleo remoto. Cada conexión tendrá historial independiente en memoria y se usará un solo proceso de Uvicorn hasta disponer de persistencia compartida. Docker publicará el servicio únicamente por Tailscale; `.env` permanecerá fuera de Git con propietario `root` y permisos `600`. La web actual es solo el cliente mínimo de diagnóstico de 22a; la PWA completa corresponde a 22c.
- Siguiente: fase 22b — Tailscale en el VPS, el PC y el iPhone.

## 2026-09-25 · Fase 22b — Tailscale en el VPS, el PC y el iPhone
- Hecho: Se comprobó Tailscale 1.102.3 en el portátil y 1.102.4 en el VPS, se reactivó el iPhone registrado como `maverick-mobile` y se verificó comunicación privada con el VPS mediante el repetidor cifrado de Madrid. Con el Wi‑Fi apagado y el iPhone en 5G, Safari abrió el cliente web, el WebSocket quedó conectado y ASTRO respondió una consulta real. Los registros del servidor identificaron el origen privado `100.85.111.116`. UFW continúa denegando toda entrada salvo `tailscale0`, ASTRO escucha solo en `100.123.43.31:8000` y una conexión a ese puerto mediante la IP pública expiró sin respuesta.
- Falló: Tailscale no consiguió establecer un enlace directo entre el portátil y el iPhone y utilizó correctamente su repetidor de Madrid, con latencias de 46 a 139 ms. La primera extracción automatizada de la IP pública usó una orden `awk` mal escapada por PowerShell y produjo una prueba inválida; se repitió sin `awk` y confirmó que el puerto público no responde.
- Decidido: El acceso remoto de ASTRO permanecerá limitado al tailnet. No se abrirán puertos del router ni se publicará el puerto 8000 del VPS. En iOS bastará mantener Tailscale activado; no se crearán reglas personalizadas de VPN On Demand mientras la reconexión automática funcione. El aviso «No seguro» de Safari corresponde al HTTP privado actual y se resolverá al incorporar HTTPS en una fase posterior.
- Siguiente: fase 22c — App web propia (PWA).

## 2026-09-25 · Fase 22c — App web propia instalable
- Hecho: Se convirtió el cliente de diagnóstico en una PWA responsive con interfaz móvil, icono SVG propio, manifiesto, service worker, streaming, coste por turno, reconexión automática e instrucciones de instalación. FastAPI sirve los recursos PWA y 15 pruebas automáticas pasan. Docker expone el núcleo en loopback y en la IP privada de Tailscale; Tailscale Serve publica `https://astro-vps.tailbee6db.ts.net/` solo dentro del tailnet y el chat usa WebSocket seguro. La app se instaló en la pantalla de inicio del iPhone, abrió sin la barra de Safari y recordó correctamente el número `381` en una conversación de dos turnos.
- Falló: En el primer despliegue, `core/api.py` se copió accidentalmente como `/opt/astro/api.py`; la web cargaba, pero el manifiesto y el service worker devolvían 404. Se eliminó el duplicado, se copió el archivo a `/opt/astro/core/api.py` y se reconstruyó el contenedor. Una comprobación posterior usó `HEAD` contra una ruta que solo admite `GET` y recibió 405; al repetirla con `GET`, el service worker respondió 200 con alcance `/`. La auditoría final encontró además un bloqueo de permisos al crear la carpeta temporal global de pytest; se repitió con una carpeta temporal aislada dentro del repositorio, pasaron las 15 pruebas y se eliminó la carpeta.
- Decidido: La PWA usará HTTPS privado mediante Tailscale Serve y nunca Funnel. El service worker almacenará solo archivos estáticos, no conversaciones. El historial seguirá asociado al WebSocket en memoria y una reconexión anunciará que comienza una sesión nueva. El icono será un SVG determinista con identidad propia.
- Siguiente: fase 22d — Panel de estado y notificaciones push.

## 2026-09-26 · Fase 22d — Panel de estado y notificaciones push

- Hecho: Se añadió a la PWA un panel con estado del núcleo, modelo activo, tiempo de funcionamiento, conexiones y controles de notificaciones. FastAPI publica las rutas de estado y Web Push; las suscripciones se validan, deduplican y conservan sin conversaciones. Se generaron claves VAPID propias, la privada se protegió como secreto de Docker y el VPS se reconstruyó con `pywebpush`. Pasaron 19 pruebas automáticas. El iPhone registró una suscripción y recibió el aviso «ASTRO está listo» con la app completamente cerrada; el servidor confirmó 1 envío y 0 fallos.
- Falló: El primer intento de generar las claves se lanzó antes de crear su carpeta. Tras restringir los permisos, el entorno aislado dejó de poder leer correctamente la clave privada. Una comprobación interna de Docker falló por el escapado de PowerShell, pero `/status` confirmó desde el contenedor que Web Push estaba configurado. La primera pulsación de «Estado» cargó JavaScript antiguo desde la caché de la PWA; una recarga permitió que el nuevo service worker tomara el control.
- Decidido: Las notificaciones usarán Web Push estándar y VAPID propio. La autorización debe iniciarla Jhony desde la PWA; la clave privada y las suscripciones permanecen fuera de Git, y los avisos no transportarán conversaciones. El panel será la base que se ampliará en fases posteriores.
- Siguiente: fase 22e — Proveedores de IA intercambiables.

## 2026-09-26 · Fase 22e — Proveedores de IA intercambiables

- Hecho: Se creó una capa común para proveedores compatibles con Responses API y se configuraron OpenAI y OpenRouter desde `config/config.yaml`, con claves separadas en `.env`. El proveedor y el modelo activos aparecen en el registro de uso, `/status` y el panel de la PWA. Pasaron 24 pruebas automáticas. Una prueba real cambió únicamente las dos líneas de proveedor y modelo, hizo que OpenRouter calculase `125 × 48 = 6000`, restauró OpenAI y obtuvo `OpenAI activo.`; el VPS reconstruido muestra `Proveedor: OpenAI` como valor predeterminado.
- Falló: Una clave de OpenRouter se pegó accidentalmente en el chat y se revocó antes de crear y guardar otra sin mostrarla. La primera petición de OpenRouter recibió 402 hasta añadir saldo. Después se detectó que OpenRouter devuelve algunas métricas de caché como `null`; se normalizaron a cero y se añadió una prueba de regresión. Las primeras transferencias paralelas al VPS activaron temporalmente la protección de SSH y dejaron archivos sin actualizar; se repitieron de forma secuencial, se compararon sus SHA-256 y coincidieron. La primera recarga de la PWA mezcló HTML nuevo con JavaScript antiguo; la segunda activó el service worker v3.
- Decidido: OpenAI seguirá siendo el proveedor predeterminado y OpenRouter será la alternativa manual. El cambio exige editar solo `proveedor` y `modelo` en el YAML y reiniciar ASTRO; no habrá conmutación automática ni envío simultáneo a dos proveedores. Cada clave permanecerá únicamente en `.env`. Al elegir OpenRouter, el contenido de la conversación transitará por OpenRouter y por el proveedor del modelo seleccionado.
- Siguiente: puerta del bloque 1 — conversación de 20 turnos coherente, dos herramientas, coste visible y uso desde la PWA del iPhone fuera de casa.
