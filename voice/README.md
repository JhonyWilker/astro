# Voice

Componentes de voz: activación, voz a texto y texto a voz.

## Voz a texto

Para transcribir una grabación local en español:

```powershell
.\.venv\Scripts\python.exe -m voice.transcribir data\audio\prueba-dispositivo-12.wav
```

El modelo se ejecuta en CPU con cuantización de 8 bits. Sus archivos se guardan bajo `data/models`, fuera de Git.

## Texto a voz

Para generar y escuchar una frase con la voz local de ASTRO:

```powershell
.\.venv\Scripts\python.exe -m voice.hablar "Hola, Jhony."
```

ASTRO usa por defecto el hablante masculino de `es_ES-sharvard-medium`. Se puede probar el femenino con `--hablante F` y generar el WAV sin reproducirlo con `--sin-reproducir`.

La voz y los audios se guardan bajo `data`, fuera de Git. La síntesis funciona localmente y no consume ninguna API.
