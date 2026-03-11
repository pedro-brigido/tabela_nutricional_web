#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/terracota}"
COMPOSE_FILE="${COMPOSE_FILE:-${APP_DIR}/docker-compose.prod.yml}"
APP_ENV_FILE="${APP_ENV_FILE:-${APP_DIR}/.env}"
STATE_FILE="${STATE_FILE:-${APP_DIR}/current-release.env}"
DATA_DIR="${DATA_DIR:-${APP_DIR}/data}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
PROJECT_NAME="${PROJECT_NAME:-tabela-nutricional}"
WEB_SERVICE="${WEB_SERVICE:-web}"
NETWORK_NAME="${NETWORK_NAME:-terracota_network}"
BACKUP_RETENTION="${BACKUP_RETENTION:-7}"
HEALTH_RETRIES="${HEALTH_RETRIES:-20}"
HEALTH_DELAY_SECONDS="${HEALTH_DELAY_SECONDS:-3}"
IMAGE_REF="${IMAGE_REF:-}"

if [[ -z "${IMAGE_REF}" ]]; then
  echo "[release] IMAGE_REF is required."
  exit 1
fi

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "[release] Compose file not found: ${COMPOSE_FILE}"
  exit 1
fi

if [[ ! -f "${APP_ENV_FILE}" ]]; then
  echo "[release] App env file not found: ${APP_ENV_FILE}"
  exit 1
fi

mkdir -p "${APP_DIR}" "${DATA_DIR}" "${BACKUP_DIR}"

if ! docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
  echo "[release] Creating Docker network: ${NETWORK_NAME}"
  docker network create "${NETWORK_NAME}" >/dev/null
fi

if [[ -n "${GHCR_READ_TOKEN:-}" ]]; then
  if [[ -z "${GHCR_USERNAME:-}" ]]; then
    echo "[release] GHCR_USERNAME is required when GHCR_READ_TOKEN is set."
    exit 1
  fi
  echo "[release] Logging into GHCR..."
  echo "${GHCR_READ_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin >/dev/null
fi

previous_image=""
if [[ -f "${STATE_FILE}" ]]; then
  previous_image="$(sed -n 's/^IMAGE_REF=//p' "${STATE_FILE}" | tail -n 1)"
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -d "${DATA_DIR}" ]] && [[ -n "$(ls -A "${DATA_DIR}" 2>/dev/null)" ]]; then
  backup_file="${BACKUP_DIR}/data-${timestamp}.tar.gz"
  echo "[release] Creating data backup: ${backup_file}"
  tar -C "${DATA_DIR}" -czf "${backup_file}" .
fi

mapfile -t backup_files < <(ls -1t "${BACKUP_DIR}"/data-*.tar.gz 2>/dev/null || true)
if (( ${#backup_files[@]} > BACKUP_RETENTION )); then
  for old_backup in "${backup_files[@]:BACKUP_RETENTION}"; do
    rm -f "${old_backup}"
  done
fi

compose_cmd=(docker compose --project-name "${PROJECT_NAME}" --env-file "${APP_ENV_FILE}" -f "${COMPOSE_FILE}")

deploy_image() {
  local target_image="$1"
  export IMAGE_REF="${target_image}"
  "${compose_cmd[@]}" pull "${WEB_SERVICE}"
  "${compose_cmd[@]}" up -d "${WEB_SERVICE}"
}

check_health() {
  local attempt
  for attempt in $(seq 1 "${HEALTH_RETRIES}"); do
    if "${compose_cmd[@]}" exec -T "${WEB_SERVICE}" python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${HEALTH_DELAY_SECONDS}"
  done
  return 1
}

save_state() {
  local deployed_image="$1"
  cat > "${STATE_FILE}" <<EOF
IMAGE_REF=${deployed_image}
DEPLOYED_AT=${timestamp}
EOF
}

echo "[release] Deploying ${IMAGE_REF}"
deploy_image "${IMAGE_REF}"

if check_health; then
  echo "[release] Health check passed."
  save_state "${IMAGE_REF}"
  echo "[release] Release completed."
  exit 0
fi

echo "[release] Health check failed for ${IMAGE_REF}."
if [[ -n "${previous_image}" ]]; then
  echo "[release] Rolling back to ${previous_image}"
  deploy_image "${previous_image}"
  if check_health; then
    echo "[release] Rollback succeeded."
    save_state "${previous_image}"
    exit 1
  fi
fi

echo "[release] Rollback failed or unavailable."
exit 1

