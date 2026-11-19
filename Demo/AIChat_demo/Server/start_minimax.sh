#!/bin/sh
set -eu

SERVER_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SERVER_DIR"

if [ -f .env.minimax ]; then
    set -a
    . ./.env.minimax
    set +a
fi

export LLM_PROVIDER="${LLM_PROVIDER:-minimax}"
export AICHAT_HOST="${AICHAT_HOST:-0.0.0.0}"
export AICHAT_PORT="${AICHAT_PORT:-8000}"
export AICHAT_ACCESS_TOKEN="${AICHAT_ACCESS_TOKEN:-123456}"

exec "${PYTHON:-python3}" main.py
