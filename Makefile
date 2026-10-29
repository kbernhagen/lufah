override VENV := .venv
override PYTHON := $(VENV)/bin/python
UV ?= $(shell "$(PYTHON)" -m pipx environment --value PIPX_BIN_DIR)/uv

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
setup: ensure-uv  # pipx install uv and sync --frozen; not required for 'make install-user'
	"$(UV)" sync --frozen

$(VENV):
	@# create minimal venv to install uv
	@python3 -c 'import sys; sys.version_info >= (3, 11) or sys.exit("Python 3.11+ required; found " + sys.version.split()[0])'
	python3 -m venv "$(VENV)"
	@# safely install pip 26.2.2
	@# https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576
	"$(PYTHON)" -m pip install "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
	@pip_version=$$($(PYTHON) -c 'import pip; print(pip.__version__)') && \
	  "$(PYTHON)" -m pip install --upgrade "pip>=$$pip_version"
	"$(PYTHON)" -m pip install pipx
	"$(PYTHON)" -m pipx ensurepath

.PHONY: ensure-uv
ensure-uv: $(VENV)
	@uv_bin_dir=$$($(PYTHON) -m pipx environment --value PIPX_BIN_DIR) || exit $$?; \
	if [ ! -x "$$uv_bin_dir/uv" ]; then \
	    "$(PYTHON)" -m pipx install uv || exit $$?; \
	fi

.PHONY: upgrade-uv
upgrade-uv: ensure-uv  # pipx install and upgrade uv
	"$(PYTHON)" -m pipx upgrade uv

.PHONY: sync
sync: ensure-uv  # uv sync
	"$(UV)" sync

.PHONY: sync-no-dev
sync-no-dev: ensure-uv  # uv sync --no-dev; for testing without dev deps
	"$(UV)" sync --no-dev

.PHONY: lint
lint: ensure-uv  # uv run pylint and ruff
	"$(UV)" run ruff check
	"$(UV)" run pylint examples scripts src tests

.PHONY: test
test: ensure-uv  # uv run pytest -vv
	"$(UV)" run pytest -vv

.PHONY: build
build: clean lint test  # clean build and test; done as-needed by other targets
	"$(UV)" build

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
	rm -rf "$(VENV)"

.PHONY: clean-all
clean-all: clean clean-venv  # clean all
	rm -rf .pytest_cache .ruff_cache
