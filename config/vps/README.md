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
