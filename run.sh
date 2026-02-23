#!/usr/bin/env bash
# Executa a aplicação usando o Python do venv gerenciado por uv.
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run: uv sync"
    exit 1
fi
exec .venv/bin/python app.py "$@"
