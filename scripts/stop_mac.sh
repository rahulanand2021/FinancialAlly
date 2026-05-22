#!/usr/bin/env bash
# Stop and remove the FinAlly Docker container (macOS / Linux).
# Usage: ./scripts/stop_mac.sh
#
# The named volume is preserved so portfolio data persists between runs.

set -euo pipefail

CONTAINER="finally"

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    docker stop "${CONTAINER}" >/dev/null
fi

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    docker rm "${CONTAINER}" >/dev/null
    echo "Container ${CONTAINER} stopped and removed (volume preserved)."
else
    echo "Container ${CONTAINER} is not present."
fi
