#!/usr/bin/env bash
# RMSE ops WATCHDOG — cron every 2 min on the VPS (the canonical copy). Alerts if a service is down,
# state has gone stale, or the brain heartbeat is old. Reuses the boss's existing Telegram bot from
# /etc/oracle/alert.env (ONE bot for Oracle + RMSE) with an [RMSE] prefix; log+journal always record.
#   --test-alert : push a harmless test line through the channel and exit (no health check).
set -u
ROOT=/opt/rmse-bot
STATE="$ROOT/state"
ALERT_LOG="$STATE/health_alert.log"
STALE_MAX_S="${STALE_MAX_S:-900}"        # 15 min: newest state file must be fresher than this
HEARTBEAT_MAX_S="${HEARTBEAT_MAX_S:-3600}"   # 1 h: brain heartbeat
ENVF=/etc/oracle/alert.env
[ -f "$ENVF" ] && . "$ENVF"

_push() {   # $1 = full message
  echo "$1" >> "$ALERT_LOG"
  logger -t rmse-watchdog "$1" 2>/dev/null
  local sent=""
  if [ -n "${ALERT_TELEGRAM_TOKEN:-}" ] && [ -n "${ALERT_TELEGRAM_CHAT:-}" ]; then
    curl -s -m 10 "https://api.telegram.org/bot${ALERT_TELEGRAM_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${ALERT_TELEGRAM_CHAT}" --data-urlencode "text=$1" >/dev/null 2>&1 && sent="telegram"
  fi
  if [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
    curl -s -m 10 -H 'Content-Type: application/json' \
      -d "{\"text\":$(printf '%s' "$1" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')}" \
      "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 && sent="${sent:+$sent+}webhook"
  fi
  echo "$sent"
}

if [ "${1:-}" = "--test-alert" ]; then
  s="$(_push "[RMSE TEST $(date -u +%Y-%m-%dT%H:%M:%SZ)] watchdog push is alive")"
  [ -z "$s" ] && { echo "no push channel configured in $ENVF (log-only)"; exit 1; }
  echo "test alert sent via: $s"; exit 0
fi

problem=""
for svc in rmse-bot rmse-brain; do
  a="$(systemctl is-active "$svc" 2>/dev/null)"
  [ "$a" != "active" ] && problem="${problem:+$problem; }$svc is '$a'"
done

# newest state json age (bot writes state every cycle / gold tick)
newest="$(ls -t "$STATE"/*.json 2>/dev/null | head -1)"
if [ -n "$newest" ]; then
  age=$(( $(date +%s) - $(stat -c %Y "$newest" 2>/dev/null || echo 0) ))
  [ "$age" -gt "$STALE_MAX_S" ] 2>/dev/null && problem="${problem:+$problem; }state stale ${age}s (>${STALE_MAX_S}s)"
fi

# brain heartbeat age
hb="$STATE/brain_heartbeat.json"
if [ -f "$hb" ]; then
  hbage=$(( $(date +%s) - $(stat -c %Y "$hb" 2>/dev/null || echo 0) ))
  [ "$hbage" -gt "$HEARTBEAT_MAX_S" ] 2>/dev/null && problem="${problem:+$problem; }brain heartbeat ${hbage}s old (>${HEARTBEAT_MAX_S}s)"
fi

[ -z "$problem" ] && exit 0
_push "[RMSE ALERT $(date -u +%Y-%m-%dT%H:%M:%SZ)] $problem" >/dev/null
exit 1
