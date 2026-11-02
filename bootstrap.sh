#!/bin/bash -e
# bootstrap uv, pipx from python 3.11+ temporary venv away from project venv
# efficiently create project venv with uv

export UV_SYSTEM_CERTS=1
export UV_MANAGED_PYTHON=1

# require python 3.11+ which supports pip 26.2.2
python3 -c 'import sys; sys.version_info >= (3, 11) or sys.exit("Python 3.11+ required; found " + sys.version.split()[0])'

set -x

# ensure old pipx home directory exists so newer pipx uses it by default on macOS
mkdir -p "$HOME/.local/pipx"

# create temporary venv
# bootstrap=$(mktemp -d)
bootstrap=".venv-bootstrap"
trap 'rm -rf "$bootstrap"' EXIT
python3 -m venv --clear "$bootstrap"

# install pinned pip; upgrade without alleged risk of downgrade due to python package
"$bootstrap/bin/pip" install \
  "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
"$bootstrap/bin/pip" install --upgrade "pip>=26.2.2"

"$bootstrap/bin/pip" install "pipx>=1.18.7" "uv>=0.13.6"

"$bootstrap/bin/pipx" ensurepath --prepend
"$bootstrap/bin/pipx" install --upgrade "pipx>=1.18.7" "uv>=0.13.6"

"$bootstrap/bin/uv" python install ">=3.15.2,<3.16"
"$bootstrap/bin/uv" sync -p ">=3.15.2,<3.16" --frozen
