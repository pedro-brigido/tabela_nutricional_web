#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/terracota}"
NETWORK_NAME="${NETWORK_NAME:-terracota_network}"

mkdir -p "${APP_DIR}" "${APP_DIR}/backups"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo "[bootstrap] Missing ${APP_DIR}/.env."
  echo "[bootstrap] Copy your production env file before the first deploy."
fi

if ! docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
  echo "[bootstrap] Creating Docker network: ${NETWORK_NAME}"
  docker network create "${NETWORK_NAME}" >/dev/null
fi

echo "[bootstrap] Done."
echo "[bootstrap] Ensure /opt/terracota/.env is populated and run deploy/release.sh via CI."
