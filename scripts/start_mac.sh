#!/usr/bin/env bash
# Start the FinAlly Docker container (macOS / Linux).
# Usage: ./scripts/start_mac.sh [--build]
#
# Builds the image if it does not exist (or if --build is passed),
# then starts the container with the persistent volume and .env file.

set -euo pipefail

IMAGE="finally:latest"
CONTAINER="finally"
VOLUME="finally-data"
PORT=8000
URL="http://localhost:${PORT}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ ! -f .env ]]; then
    echo "ERROR: .env not found in ${PROJECT_ROOT}. Copy .env.example to .env first." >&2
    exit 1
fi

FORCE_BUILD=false
for arg in "$@"; do
    if [[ "${arg}" == "--build" ]]; then
        FORCE_BUILD=true
    fi
done

if [[ "${FORCE_BUILD}" == "true" ]] || ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    echo "Building image ${IMAGE}..."
    docker build -t "${IMAGE}" .
fi

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "Container ${CONTAINER} already running at ${URL}"
    exit 0
fi

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    docker rm "${CONTAINER}" >/dev/null
fi

docker run -d \
    --name "${CONTAINER}" \
    --env-file .env \
    -p "${PORT}:8000" \
    -v "${VOLUME}:/app/db" \
    --restart unless-stopped \
    "${IMAGE}" >/dev/null

echo "FinAlly started at ${URL}"

if command -v open >/dev/null 2>&1; then
    open "${URL}" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${URL}" >/dev/null 2>&1 || true
fi
