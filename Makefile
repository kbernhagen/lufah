VENV = .venv
PYTHON = $(VENV)/bin/python

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  install      install for all users; may not have permission"
	@echo "  install-user install via pipx for current user"
	@echo "  install-dev  like install-user, but is live linked to source code"
	@echo "  build        build py package; done as-needed by other targets"
	@echo "  clean        remove all build products"

build: venv
	"$(PYTHON)" -m build

venv: "$(VENV)"

"$(VENV)":
	python3 -m venv "$(VENV)"
	"$(PYTHON)" -m pip install --upgrade pip
	"$(PYTHON)" -m pip install --upgrade build twine pipx

install-dev: venv
	"$(PYTHON)" -m pipx install --editable .

install-user: venv
	"$(PYTHON)" -m pipx install .

install:
	python3 -m pip install .

publish-testpypi: build
	"$(PYTHON)" -m twine upload -u __token__ --repository testpypi dist/*

publish-pypi: build
	"$(PYTHON)" -m twine upload -u __token__ dist/*

clean:
	rm -rf dist build *.egg-info lufah/__pycache__ examples/__pycache__ "$(VENV)"
