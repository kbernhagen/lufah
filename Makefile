VENV := .venv
PYTHON := $(VENV)/bin/python

.PHONY: help
help:
	@echo "Please use \`make <target>' where <target> is one of"
	@grep -E '^[a-zA-Z_-]+:.*?# .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?# "}; {printf "  %-14s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

.PHONY: venv
venv: $(VENV)  # create dev venv; does not install dependencies

$(VENV):
	python3 -m venv "$(VENV)"
	"$(PYTHON)" -m pip install --upgrade pip
	# install base dev dependencies
	"$(PYTHON)" -m pip install --upgrade build pipx twine
	@echo "You may need to use \"source $(VENV)/bin/activate\""

.PHONY: build
build: clean $(VENV)
	@# clean build package; done as-needed by other targets
	"$(PYTHON)" -m build

.PHONY: install-dev
install-dev: $(VENV)  # dev install with deps in venv; live linked to source code
	"$(PYTHON)" -m pip install --editable ".[dev]"
	@echo "You may need to use \"source $(VENV)/bin/activate\""

.PHONY: install-user
install-user: $(VENV)  # install non-dev via pipx for current user
	"$(PYTHON)" -m pipx install --force .

.PHONY: install
install:  # install for all users; you may need sudo
	python3 -m pip install .

.PHONY: publish-testpypi
publish-testpypi: build
	"$(PYTHON)" -m twine upload -u __token__ --repository testpypi dist/*

.PHONY: publish-pypi
publish-pypi: build  # build and publish to pypi.org
	"$(PYTHON)" -m twine upload -u __token__ dist/*

.PHONY: clean
clean:  # remove all build products
	rm -rf dist build *.egg-info lufah/__pycache__ examples/__pycache__
	rm -rf src/*.egg-info src/*/__pycache__

.PHONY: clean-venv
clean-venv:  # remove dev venv
	rm -rf "$(VENV)"

.PHONY: clean-all
clean-all: clean clean-venv  # clean all
