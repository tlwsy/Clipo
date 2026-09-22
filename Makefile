# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
PYTHON ?= python3
VENV := .venv/bin

.PHONY: install configure dev serve build lint fmt test migrate upgrade gen-api up down extension-package

install:
	@test -x $(VENV)/python || uv venv --python $(PYTHON) .venv
	uv pip install --python $(VENV)/python -r backend/requirements.lock -e './backend[dev]'
	npm --prefix frontend ci

configure:
	$(PYTHON) scripts/init_env.py

dev: upgrade
	$(VENV)/python scripts/dev.py

serve: upgrade
	$(VENV)/python -m app.serve

build:
	npm --prefix frontend run build

lint:
	$(VENV)/ruff check --config backend/pyproject.toml backend scripts
	$(VENV)/black --config backend/pyproject.toml --check backend scripts
	npm --prefix frontend run lint
	node extension/scripts/check.mjs

fmt:
	$(VENV)/black --config backend/pyproject.toml backend scripts
	$(VENV)/ruff check --config backend/pyproject.toml --fix backend scripts
	npm --prefix frontend run fmt

test:
	$(VENV)/pytest backend/tests
	npm --prefix frontend test
	node --test extension/tests/*.test.mjs

upgrade:
	$(VENV)/alembic -c backend/alembic.ini upgrade head

migrate:
	@test -n "$(m)" || (echo 'Usage: make migrate m="description"'; exit 1)
	$(VENV)/alembic -c backend/alembic.ini revision --autogenerate -m "$(m)"

gen-api:
	$(VENV)/python backend/scripts/export_openapi.py
	npm --prefix frontend run gen-api

up:
	docker compose up --build -d

down:
	docker compose down

extension-package:
	$(PYTHON) scripts/package_extension.py
