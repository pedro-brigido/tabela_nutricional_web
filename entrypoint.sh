#!/bin/sh
# Roda migrações e seed antes de iniciar o Gunicorn.
# Assim todo deploy (ou restart) deixa o banco atualizado.
set -e

export FLASK_APP="${FLASK_APP:-wsgi:app}"

echo "[entrypoint] Aplicando migrações..."
flask db upgrade || {
    echo "[entrypoint] Migração falhou. Tentando stamp head e upgrade..."
    flask db stamp head
    flask db upgrade
}

echo "[entrypoint] Garantindo planos no banco..."
flask seed-plans

echo "[entrypoint] Iniciando Gunicorn..."
exec gunicorn -c gunicorn.conf.py wsgi:app
