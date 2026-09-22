#!/bin/sh
# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
set -eu
alembic -c /app/backend/alembic.ini upgrade head
export CLIPO_BIND_HOST=0.0.0.0
exec python -m app.serve
