# Config

Configuración de ASTRO sin incluir claves ni contraseñas.

- `config.yaml`: modelo, idioma y límites operativos.
- `personality.md`: identidad, trato, tono, criterio y reglas de privacidad que ASTRO recibe en cada respuesta.
- `personality-restricted.md`: identidad neutra y reglas de aislamiento para dispositivos que no pueden acceder a los datos de Jhony.

Los valores de `config.yaml` se leen al arrancar. Para cambiar el modelo, edita `modelo` y reinicia ASTRO; no es necesario modificar Python.

Las tarifas de `precios_usd_por_millon` corresponden al modelo y nivel de servicio configurados. Deben revisarse al cambiar de modelo o cuando OpenAI actualice sus precios.

La sección `api` controla el tiempo máximo por intento y los reintentos automáticos del SDK. El valor de `reintentos` debe estar entre 0 y 5.

`zona_horaria` usa un nombre IANA, como `Europe/Madrid`, para aplicar automáticamente el horario de invierno y de verano.

La sección `agente` limita cuántas herramientas puede encadenar ASTRO dentro de un solo turno. `pasos_herramienta_maximos` debe estar entre 1 y 10.
