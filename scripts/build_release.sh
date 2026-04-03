#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]] && .venv/bin/python -c "import PIL" >/dev/null 2>&1; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

if [[ -x ".venv/bin/pyinstaller" ]]; then
  PYINSTALLER=".venv/bin/pyinstaller"
else
  PYINSTALLER="pyinstaller"
fi

"$PYTHON" scripts/generate_icons.py
"$PYINSTALLER" --noconfirm --clean documentos_empresa_app.spec

echo
case "$(uname -s)" in
  Darwin)
    echo "Build macOS concluido em: $ROOT_DIR/dist/G-docs"
    echo "Icone de empacotamento: assets/icons/icon.icns"
    ;;
  Linux)
    echo "Build Linux concluido em: $ROOT_DIR/dist/G-docs"
    echo "Icone da interface/desktop integration: assets/icons/icon.png"
    ;;
  *)
    echo "Build concluido em: $ROOT_DIR/dist/G-docs"
    ;;
esac
