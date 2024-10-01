VENV := .venv
PYTHON := $(VENV)/bin/python
UV := ${HOME}/.local/bin/uv

.PHONY: help
help:
	@echo "make targets:"
	@grep -E '^[a-zA-Z_-]+:.*?# .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?# "}; {printf "  %-14s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

.PHONY: install-user
install-user: $(VENV)  # install via pipx for current user; does not need setup
	"$(PYTHON)" -m pipx install --force .

.PHONY: uninstall-user
uninstall-user: $(VENV)  # uninstall via pipx for current user; does not need setup
	"$(PYTHON)" -m pipx uninstall lufah

.PHONY: setup
setup: $(VENV) $(UV)  # pipx install uv and sync --frozen; not required for 'make install-user'
	"$(UV)" sync --frozen

$(VENV):
	@# create minimal venv to install uv
	python3 -m venv "$(VENV)"
	"$(PYTHON)" -m ensurepip --upgrade
	"$(PYTHON)" -m pip install pipx
	"$(PYTHON)" -m pipx ensurepath
	@echo "You may want to use \"source $(VENV)/bin/activate\""

$(UV): $(VENV)
	@if [ ! -x "$(UV)" ]; then \
	    "$(PYTHON)" -m pipx install uv; \
	fi

upgrade-uv: $(UV)  # pipx install and upgrade uv
	"$(PYTHON)" -m pipx upgrade uv

.PHONY: sync
sync:  # uv sync
	"$(UV)" sync

.PHONY: sync-no-dev
sync-no-dev:  # uv sync --no-dev; for testing without dev deps
	"$(UV)" sync --no-dev

.PHONY: lint
lint:  # uv run pylint and ruff
	"$(UV)" run ruff check
	"$(UV)" run pylint examples scripts src tests

.PHONY: test
test:  # uv run pytest -vv
	"$(UV)" run pytest -vv

.PHONY: build
build: clean lint test  # clean build and check; done as-needed by other targets
	# uv build requires uv >= 0.4.5; if build fails, try 'make upgrade-uv'
	"$(UV)" build
	"$(UV)" run twine check dist/*

.PHONY: install-system
install-system:  # install for all users; you may need sudo; you must have venv deactivated
	python3 -m pip install .

.PHONY: publish-testpypi
publish-testpypi: build
	"$(UV)" run twine upload -u __token__ --repository testpypi dist/*

.PHONY: publish
publish: build  # build and publish to pypi.org
	"$(UV)" run twine upload -u __token__ dist/*

.PHONY: clean
clean:  # remove all build products
	rm -rf dist build src/*.egg-info examples/__pycache__
	find src -type d -name __pycache__ -print -exec rm -r {} \; -prune

.PHONY: clean-venv
clean-venv:  # remove venv
	rm -rf "$(VENV)"

.PHONY: clean-all
clean-all: clean clean-venv  # clean all
	rm -rf .ruff_cache
