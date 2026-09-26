# Operación del VPS de ASTRO

El VPS ejecuta Ubuntu Server LTS y solo acepta tráfico entrante por la interfaz privada `tailscale0`. Las credenciales permanecen en `.secrets/`, ignorado por Git.

## Comprobaciones

```bash
ufw status verbose
tailscale status
systemctl status astro-backup.timer
journalctl -u astro-backup.service --no-pager
```

## Copia manual

```bash
systemctl start astro-backup.service
```

## Consultar instantáneas

```bash
RESTIC_PASSWORD_FILE=/root/.config/restic/astro-password \
RESTIC_REPOSITORY=rclone:astro-drive:ASTRO-backups/restic \
restic snapshots
```

## Restauración

Las restauraciones deben hacerse primero en una carpeta temporal y compararse con los archivos activos antes de sustituir nada. La contraseña de recuperación tiene una copia local en `.secrets/backups/restic_password` y nunca debe subirse a Git.

## Núcleo de ASTRO

El proyecto desplegado vive en `/opt/astro` y se ejecuta con Docker Compose. El contenedor funciona con un usuario sin privilegios, sistema de archivos de solo lectura, capacidades Linux eliminadas y reinicio automático salvo detención manual.

El archivo `/opt/astro/.env` pertenece a `root`, tiene permisos `600` y no se guarda en Git. El puerto 8000 se publica únicamente en `127.0.0.1` para el proxy HTTPS y en `100.123.43.31`, la IP privada de Tailscale; nunca en la interfaz pública.

### Estado y registros

```bash
cd /opt/astro
docker compose ps
docker compose logs --tail=100 astro
curl http://100.123.43.31:8000/health
```

### Reinicio controlado

```bash
cd /opt/astro
docker compose restart astro
docker compose ps
```

## HTTPS privado

Tailscale Serve publica la PWA solo dentro del tailnet y reenvía HTTPS al núcleo local:

```text
https://astro-vps.tailbee6db.ts.net/
```

Comprobación:

```bash
tailscale serve status
curl http://127.0.0.1:8000/health
```

La configuración persistente se creó con:

```bash
tailscale serve --bg 8000
```

No debe sustituirse por Tailscale Funnel: Funnel haría el servicio accesible desde Internet. El nombre técnico del certificado aparece en los registros públicos de certificados, pero el contenido y el acceso continúan siendo privados.

## Notificaciones Web Push

La clave privada VAPID vive en:

```text
/opt/astro/.secrets/vapid/private_key.pem
```

Docker la monta como secreto de solo lectura. La clave pública y el asunto VAPID están en `/opt/astro/.env.vapid`, con propietario `root` y permisos `600`. Ninguno de estos archivos se sube a Git.

Las suscripciones se guardan en `/opt/astro/data/push_subscriptions.json`. Para comprobar el sistema sin mostrar secretos:

```bash
curl https://astro-vps.tailbee6db.ts.net/status
```

El campo `push.configured` debe ser `true`. El número de suscripciones puede consultarse en `push.subscriptions`.

Antes de cada actualización se ejecutan las pruebas en el portátil. Después se copian únicamente los archivos versionados, se valida la configuración y se reconstruye el servicio:

```bash
cd /opt/astro
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
```
