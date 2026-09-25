# Registros locales

ASTRO guarda en `uso.jsonl` una línea JSON por petición terminada con tokens, tiempo y coste estimado.

Los errores controlados se guardan en `errores.jsonl` con fecha, tipo, estado HTTP, código y si son recuperables.

No se almacenan preguntas, respuestas, mensajes de error completos, claves ni contraseñas. Los archivos JSONL son datos locales de ejecución y no se suben a Git.
