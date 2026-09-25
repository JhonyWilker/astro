# Tools

Herramientas que ASTRO puede usar para consultar información y ejecutar acciones.

## Añadir una herramienta

Cada herramienta vive en un único archivo Python de esta carpeta y exporta una variable `HERRAMIENTA` del tipo definido en `base.py`. Esa ficha contiene nombre, descripción, esquema de parámetros, riesgo y función ejecutora.

`registro.py` descubre los archivos automáticamente al arrancar. No hay que editar `core/chat.py` ni mantener una lista manual.

Niveles de riesgo disponibles:

- `bajo`: consulta o cálculo sin cambios externos.
- `medio`: cambio externo reversible o de impacto limitado.
- `alto`: acción sensible, privada, económica o difícil de revertir.

El riesgo queda registrado como metadato. Las reglas de permiso `AUTO`, `ASK` y `DENY` se implementarán en la fase 53.

Herramientas actuales:

- `fecha_hora.py`: consulta el reloj local en la zona configurada; riesgo bajo.
- `calculadora.py`: evalúa únicamente aritmética permitida y devuelve un resultado exacto sin usar `eval`; riesgo bajo.
