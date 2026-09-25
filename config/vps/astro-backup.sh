#!/usr/bin/env bash
set -euo pipefail

export RESTIC_PASSWORD_FILE=/root/.config/restic/astro-password
export RESTIC_REPOSITORY=rclone:astro-drive:ASTRO-backups/restic

restic backup /etc /root /home /opt \
  --exclude=/root/.cache \
  --exclude=/root/.config/rclone/rclone.conf \
  --exclude=/root/.config/restic/astro-password \
  --tag astro-vps

restic forget \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 6 \
  --prune
