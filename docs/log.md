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
