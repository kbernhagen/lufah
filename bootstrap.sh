#!/bin/bash -e
# bootstrap pipx install uv from patched python 3.11.18+
# efficiently create project venv with uv

export UV_MANAGED_PYTHON=1

# require a patched python 3.11-3.15; 3.16 is not supported
# current patched versions are 3.11.18, 3.12.16, 3.13.18, 3.14.10, 3.15.2
python3 - <<'PY'
import sys

version = sys.version_info
patched_minor_floors = {11: 18, 12: 16, 13: 18, 14: 10, 15: 2}
is_supported = (
    version.major == 3
    and version.minor in patched_minor_floors
    and version.micro >= patched_minor_floors[version.minor]
)
if not is_supported:
    sys.exit(
        "Patched Python 3.11-3.15 required; found "
        f"{version.major}.{version.minor}.{version.micro}"
    )
PY

set -x

# ensure old pipx home directory exists so newer pipx uses it by default on macOS
mkdir -p "$HOME/.local/pipx"

# create temporary venv
# bootstrap=$(mktemp -d)
bootstrap=".venv-bootstrap"
trap 'rm -rf "$bootstrap"' EXIT
python3 -m venv --clear "$bootstrap"

"$bootstrap/bin/pip" install --upgrade "pip>=26.2.2"
"$bootstrap/bin/pip" install "pipx>=1.18.7" "uv>=0.13.6"

"$bootstrap/bin/pipx" ensurepath
# we used to install pipx, which can be insecure
"$bootstrap/bin/pipx" uninstall pipx || true
# this can fail if uv is not managed by pipx
"$bootstrap/bin/pipx" install --upgrade "uv>=0.13.6" || true

"$bootstrap/bin/uv" sync -p ">=3.15.2,<3.16" --frozen
