#!/usr/bin/env bash
# Event Tracker — automated nightly backup with rotation.
# Pulls /api/backup into BACKUP_DIR and keeps the newest KEEP copies.
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8093}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/event-tracker}"
KEEP="${KEEP:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/event-tracker-$STAMP.zip"

# Fail loudly if the app is down or returns non-200 — don't save an error page as a "backup".
HTTP_CODE=$(curl -s -o "$OUT" -w "%{http_code}" --max-time 60 "$APP_URL/api/backup") || HTTP_CODE=000
if [ "$HTTP_CODE" != "200" ]; then
  rm -f "$OUT"
  echo "[$(date)] Backup FAILED — HTTP $HTTP_CODE from $APP_URL" >&2
  exit 1
fi

# Sanity: verify it's a valid zip containing the DB before trusting it.
if ! unzip -l "$OUT" | grep -q "events.db"; then
  rm -f "$OUT"
  echo "[$(date)] Backup FAILED — zip invalid or missing events.db" >&2
  exit 1
fi

# Rotate: delete everything beyond the newest $KEEP.
# (while-read, not xargs -r: that flag is GNU-only and errors on macOS)
ls -1t "$BACKUP_DIR"/event-tracker-*.zip 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old"
done

echo "[$(date)] Backup OK — $OUT ($(du -h "$OUT" | cut -f1)), $(ls "$BACKUP_DIR" | wc -l | tr -d ' ') kept"
