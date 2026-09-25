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

El archivo `/opt/astro/.env` pertenece a `root`, tiene permisos `600` y no se guarda en Git. El puerto se publica exclusivamente en `100.123.43.31:8000`, la IP privada de Tailscale.

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

Antes de cada actualización se ejecutan las pruebas en el portátil. Después se copian únicamente los archivos versionados, se valida la configuración y se reconstruye el servicio:

```bash
cd /opt/astro
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
```
