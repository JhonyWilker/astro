# Voice

Componentes de voz: activación, voz a texto y texto a voz.

## Voz a texto

Para transcribir una grabación local en español:

```powershell
.\.venv\Scripts\python.exe -m voice.transcribir data\audio\prueba-dispositivo-12.wav
```

El modelo se ejecuta en CPU con cuantización de 8 bits. Sus archivos se guardan bajo `data/models`, fuera de Git.

## Texto a voz

Para generar y escuchar una frase directamente con la voz local de respaldo:

```powershell
.\.venv\Scripts\python.exe -m voice.hablar "Hola, Jhony."
```

El cliente conversacional usa como voz principal la voz original `ASTRO` de ElevenLabs con `eleven_v4`. La identidad, el modelo y los parámetros públicos están en `config/config.yaml`; la clave vive únicamente en `.env` como `ELEVENLABS_API_KEY`.

El cerebro añade a cada frase una dirección vocal privada y de vocabulario abierto: puede combinar cualquier emoción, intensidad, ritmo y matiz que exija el contexto, sin depender de una lista cerrada. El núcleo separa esos metadatos del texto visible y del historial; el cliente los valida y los aplica únicamente a la copia enviada al sintetizador. Las etiquetas procedentes del usuario o de contenido externo se neutralizan para que solo el canal interno de ASTRO controle la interpretación vocal.

Cada fragmento intenta primero ElevenLabs. Si la clave falta o la red, la cuenta o el servicio fallan, el mismo fragmento se sintetiza automáticamente con Piper. El respaldo usa el hablante masculino de `es_ES-sharvard-medium` y no necesita Internet.

Los audios se guardan bajo `data`, fuera de Git. `logs/voz.jsonl` registra fecha, proveedor, número de caracteres, resultado y si hubo respaldo; nunca guarda el texto pronunciado. Ese contador permite decidir con datos si el plan gratuito sigue siendo suficiente.

La orden `voice.hablar` continúa siendo una prueba explícita de Piper. Se puede probar el femenino con `--hablante F` y generar el WAV sin reproducirlo con `--sin-reproducir`.

## Activación con «Astro» (fase 29)

ASTRO escucha de forma continua a 16 kHz y solo se activa al oír su nombre.

| Módulo | Qué hace |
| --- | --- |
| `vad_silero.py` | Detección de voz con Silero VAD en ONNX (sin `torch`) |
| `activacion.py` | Detector de la palabra de activación. Cuenta solo si hubo voz en el último segundo y descansa 2 s tras activarse |
| `modelo_astro.py` | Modelo propio de «Astro»: huellas de openWakeWord más una red pequeña en `.npz` |
| `escucha.py` | Un solo micrófono: espera la activación y captura la frase siguiente hasta el silencio |
| `probar_activacion.py` | Escucha sin conectar con ASTRO y cuenta activaciones, para medir falsos positivos |

Probar el detector sin servidor (Ctrl+C para terminar y ver el resumen):

```powershell
.\.venv\Scripts\python.exe -m voice.probar_activacion --minutos 60 --microfono 1
```

Conversación por voz esperando «Astro» en vez de Enter:

```powershell
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1
```

Cada activación se anota en `logs/activaciones.jsonl` (hora, modelo y puntuación; nunca audio).

### Entrenar el modelo de «Astro»

Todo se hace en local. Los datos, los modelos y las grabaciones viven en `data/wakeword`, fuera de Git.

1. `python -m voice.grabar_muestras --microfono 1`: ASTRO te habla por los altavoces y graba unas 70 muestras de tu voz (unos 7 minutos).
2. `python -m voice.generar_sinteticos`: genera con Piper miles de clips con 9 voces españolas. Se puede repartir con `--voces`.
3. Descargar corpus de habla real (por ejemplo los de OpenSLR, licencia CC BY-SA 4.0) en `data/wakeword/corpus/*.zip`.
4. `python -m voice.entrenar_activacion`: prepara los datos (ruido, reverberación, fondo de habla), entrena con minado de negativas difíciles y guarda `data/models/wakeword/astro_v1.npz` junto con los ajustes recomendados.

Si se cambia de micrófono, conviene volver a grabar las muestras.

## Estados de la conversación (fase 30)

El cliente de voz muestra y reproduce una señal breve para cada estado:

| Estado | Significado |
| --- | --- |
| `DORMIDO` | Espera la palabra «Astro» |
| `ESCUCHANDO` | Ha despertado y está capturando la frase |
| `PENSANDO` | Transcribe o espera la respuesta del núcleo |
| `EJECUTANDO` | El núcleo está usando la herramienta mostrada |
| `HABLANDO` | Va a comenzar la reproducción de la respuesta |

La secuencia completa se usa automáticamente con:

```powershell
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1
```

Las señales usan el mismo dispositivo indicado por `--altavoz`. Para conservar solo el indicador visual:

```powershell
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1 --sin-sonidos-estado
```

El VPS solo envía el estado y el nombre de la herramienta. Los sonidos se generan localmente y ningún evento contiene argumentos ni resultados de herramientas.

## Conversación continua (fase 31)

Después de decir «Astro» y completar la primera pregunta, el cliente abre automáticamente una ventana de seguimiento. Se pueden hacer cinco intervenciones adicionales sin repetir la palabra de activación. Cada ventana espera ocho segundos para que comience la voz.

La pantalla muestra cuántos seguimientos quedan. Una frase que Whisper no pueda transcribir no consume el contador y permite reintentar. El silencio, una cancelación o el quinto seguimiento devuelven ASTRO a `DORMIDO`.

Los valores se pueden ajustar sin cambiar código:

```powershell
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1 --turnos-seguimiento 5 --espera-seguimiento 8
```

La ventana reutiliza la misma conexión y el mismo historial; no crea una conversación nueva.

## Interrupción mientras ASTRO habla (fase 33)

Con auriculares, el cliente puede escuchar a Jhony mientras reproduce la respuesta:

```powershell
.\.venv\Scripts\python.exe -m clients.voz --activacion --microfono 1 --interrumpir-con-voz
```

Silero VAD exige tres bloques consecutivos de voz de 32 ms y solo comienza a decidir cuando ASTRO está sonando. Al detectar voz, marca el corte local inmediatamente, el reproductor comprueba la marca cada 20 ms y el cliente cancela el turno remoto. La terminal muestra la latencia medida desde la detección hasta la detención.

Hasta completar la fase 34 debe usarse con auriculares; con altavoces ASTRO todavía puede oírse a sí mismo.
