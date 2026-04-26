SHELL := cmd.exe
.SHELLFLAGS := /C
.DEFAULT_GOAL := help

.PHONY: help install backend frontend dev test test-ui test-e2e build audit-install audit-security audit-eval audit-redteam audit-drift audit-all

help:
	@echo Targets disponibles:
	@echo   make install   Instala dependencias de backend y frontend.
	@echo   make backend   Arranca FastAPI en modo reload.
	@echo   make frontend  Arranca Vite en modo desarrollo.
	@echo   make dev       Abre backend y frontend en dos ventanas de consola.
	@echo   make test      Ejecuta los tests Python.
	@echo   make test-ui   Ejecuta los tests del frontend.
	@echo   make test-e2e  Ejecuta los tests E2E con Playwright.
	@echo   make build     Compila el frontend.
	@echo   make audit-install  Instala dependencias opcionales de auditoria.
	@echo   make audit-security Ejecuta semgrep y bandit.
	@echo   make audit-eval     Ejecuta DeepEval y Promptfoo.
	@echo   make audit-redteam  Ejecuta Garak.
	@echo   make audit-drift    Genera reporte de drift (Evidently opcional).
	@echo   make audit-all      Ejecuta pipeline completo de auditoria.

install:
	python -m pip install -e .[dev]
	cd /d frontend && npm install

backend:
	uvicorn visor_agentico.main:app --reload

frontend:
	cd /d frontend && npm run dev

dev:
	start "visor-backend" cmd /k "cd /d $(CURDIR) && uvicorn visor_agentico.main:app --reload"
	start "visor-frontend" cmd /k "cd /d $(CURDIR)\frontend && npm run dev"

test:
	python -m pytest

test-ui:
	cd /d frontend && npm run test

test-e2e:
	cd /d frontend && npm run test:e2e

build:
	cd /d frontend && npm run build

audit-install:
	python -m pip install -e .[audit]

audit-security:
	python scripts/audit/run_security_scans.py

audit-eval:
	python scripts/audit/run_deepeval_suite.py
	python scripts/audit/run_promptfoo_regression.py

audit-redteam:
	python scripts/audit/run_garak_redteam.py

audit-drift:
	python scripts/audit/run_drift_report.py --use-evidently

audit-all:
	python scripts/audit/run_all.py
