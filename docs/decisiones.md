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
