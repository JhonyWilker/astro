# Clientes

Los clientes no contienen el cerebro de ASTRO. Se conectan por WebSocket al mismo núcleo que vive en el VPS y cada conexión mantiene su propio historial en memoria.

## Terminal

En PowerShell:

```powershell
$env:ASTRO_WS_URL="ws://100.123.43.31:8000/ws"
.\.venv\Scripts\python.exe -m clients.terminal
```

Escribe `salir` para cerrar. La variable `ASTRO_WS_URL` permite cambiar la dirección sin modificar código.

## Navegador

Abre esta dirección desde un dispositivo conectado a la red privada de Tailscale:

```text
http://100.123.43.31:8000/
```

La página es un cliente de diagnóstico mínimo para la fase 22a. La aplicación web instalable en el iPhone se construirá en la fase 22c.

## Acceso

El puerto 8000 está enlazado únicamente a la IP privada de Tailscale del VPS. No está publicado en la interfaz pública.

## iPhone fuera de casa

1. Instala Tailscale desde la App Store e inicia sesión con la misma cuenta del tailnet de ASTRO.
2. Mantén Tailscale conectado.
3. Abre `http://100.123.43.31:8000/` en Safari.
4. Para comprobar el acceso exterior, apaga el Wi‑Fi y realiza una consulta mediante 4G o 5G.

Tailscale para iOS conserva automáticamente la conexión mientras permanece activado. No se necesita abrir ningún puerto del router ni del VPS. Safari muestra «No seguro» porque la dirección usa HTTP; el acceso continúa restringido al túnel privado cifrado. HTTPS y la aplicación instalable se tratarán en las fases posteriores.
