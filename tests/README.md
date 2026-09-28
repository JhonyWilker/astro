# Tests

Pruebas automáticas que comprueban configuración, coste, herramientas, errores y bucle de agente sin usar internet, consumir la API ni leer secretos.

Ejecutar desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Las pruebas de audio usan un micrófono simulado: comprueban el formato WAV, la duración y los límites sin acceder al micrófono real. La captura física se valida por separado en el equipo local.

Las pruebas de transcripción usan un modelo simulado: comprueban segmentos, configuración y errores sin descargar modelos ni procesar voz real.

Las pruebas de síntesis usan una voz y una salida de audio simuladas: verifican el WAV, el hablante y la reproducción sin cargar Piper ni emitir sonido.
