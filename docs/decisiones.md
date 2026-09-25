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
