#!/usr/bin/env bash
# Helper to run Flask CLI commands with clean Python environment.
# Usage: ./run_flask.sh db migrate -m "initial"
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BASE="$(readlink -f "$DIR/.venv/bin/python" | xargs dirname)"
exec env -i \
  HOME="$HOME" \
  PATH="$PYTHON_BASE:$HOME/.local/bin:/usr/bin:/bin" \
  VIRTUAL_ENV="$DIR/.venv" \
  PYTHONPATH="$DIR/.venv/lib/python3.11/site-packages:$DIR/src" \
  FLASK_ENV="${FLASK_ENV:-development}" \
  FLASK_APP=wsgi:app \
  "$DIR/.venv/bin/python" -m flask "$@"
