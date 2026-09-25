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
