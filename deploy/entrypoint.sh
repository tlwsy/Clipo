#!/bin/sh
set -eu
alembic -c /app/backend/alembic.ini upgrade head
export CLIPO_BIND_HOST=0.0.0.0
exec python -m app.serve
