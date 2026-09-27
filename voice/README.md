# Voice

Componentes de voz: activación, voz a texto y texto a voz.

## Voz a texto

Para transcribir una grabación local en español:

```powershell
.\.venv\Scripts\python.exe -m voice.transcribir data\audio\prueba-dispositivo-12.wav
```

El modelo se ejecuta en CPU con cuantización de 8 bits. Sus archivos se guardan bajo `data/models`, fuera de Git.
