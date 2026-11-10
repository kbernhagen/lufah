override VENV := .venv
override PYTHON := $(VENV)/bin/python
UV ?= $(HOME)/.local/bin/uv

export UV_MANAGED_PYTHON=1

.PHONY: help
help:
	@echo "make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?# .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?# "}; {printf "  %-14s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

.PHONY: install-user
install-user: uninstall-user  # (re)install lufah via uv for current user
	"$(UV)" tool install -p ">=3.15.2,<3.16" --force .  # force to ensure latest is installed
	"$(PYTHON)" -m pipx ensurepath

.PHONY: uninstall-user
uninstall-user: ensure-uv  # uninstall via pipx and uv for current user
	"$(UV)" tool uninstall lufah || true
	"$(PYTHON)" -m pipx uninstall lufah || true

.PHONY: ensure-uv
ensure-uv:
	@if [ ! -x "$(UV)" ]; then /bin/bash ./bootstrap.sh; fi

.PHONY: upgrade-uv
upgrade-uv: ensure-uv  # pipx install/upgrade uv; expect an error if uv is not managed by pipx
	"$(UV)" run python -m pipx upgrade uv

.PHONY: sync
sync: ensure-uv  # uv sync
	"$(UV)" sync -p ">=3.15.2,<3.16"

.PHONY: sync-no-dev
sync-no-dev: ensure-uv  # uv sync --no-dev; for testing without dev deps
	"$(UV)" sync --no-dev -p ">=3.15.2,<3.16"

.PHONY: lint
lint: ensure-uv  # uv run pylint and ruff
	"$(UV)" run ruff check
	"$(UV)" run pylint examples scripts src tests

.PHONY: test
test: ensure-uv  # uv run pytest -vv
	"$(UV)" run pytest -vv

.PHONY: build
build: clean lint test  # clean build and test; done as-needed by other targets
	"$(UV)" build --clear

.PHONY: publish-test
publish-test: build  # build and publish to test.pypi.org
	@set -e; \
	token="$$( "$(PYTHON)" -c 'import getpass; print(getpass.getpass("TestPyPI API token: "), end="")' )"; \
	if [ -z "$$token" ]; then echo "No token entered." >&2; exit 1; fi; \
	UV_PUBLISH_TOKEN="$$token" "$(UV)" publish --publish-url https://test.pypi.org/legacy/

.PHONY: publish
publish: build  # build and publish to pypi.org
	@set -e; \
	token="$$( "$(PYTHON)" -c 'import getpass; print(getpass.getpass("PyPI API token: "), end="")' )"; \
	if [ -z "$$token" ]; then echo "No token entered." >&2; exit 1; fi; \
	UV_PUBLISH_TOKEN="$$token" "$(UV)" publish

.PHONY: clean
clean:  # remove all build products
	rm -rf dist build src/*.egg-info
	find . -type d -name __pycache__ -print -exec rm -r {} \; -prune

.PHONY: clean-venv
clean-venv:  # remove venv
	rm -rf "$(VENV)" .venv-bootstrap

.PHONY: clean-all
clean-all: clean clean-venv  # clean all
	rm -rf .pytest_cache .ruff_cache
