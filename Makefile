.PHONY: install install-api install-web migrate seed test dev

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

install: install-api install-web

install-api:
	cd apps/api && python -m venv .venv
	cd apps/api && .venv/Scripts/pip install -r requirements.txt || .venv/bin/pip install -r requirements.txt

install-web:
	cd apps/web && npm install

migrate:
	cd apps/api && (.venv/Scripts/python -m alembic upgrade head || .venv/bin/python -m alembic upgrade head)

seed:
	cd apps/api && (.venv/Scripts/python -m app.db.seed || .venv/bin/python -m app.db.seed)

test:
	cd apps/api && (.venv/Scripts/python -m pytest -q || .venv/bin/python -m pytest -q)

dev:
	@echo "Use: powershell -File scripts/dev.ps1  (Windows) or  bash scripts/dev.sh"
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1
