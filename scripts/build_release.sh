#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_TESTS="${RUN_TESTS:-1}"
DIST_DIR="$ROOT_DIR/dist/DocFLow"
DIST_RELEASE_DIR="$ROOT_DIR/dist_release"

cd "$ROOT_DIR"

python_supports_modules() {
  local candidate="$1"
  "$candidate" - <<'PY' >/dev/null 2>&1
import importlib.util
import os
import sys

required_modules = tuple(filter(None, os.environ["REQUIRED_MODULES"].split(",")))
missing = [name for name in required_modules if importlib.util.find_spec(name) is None]
sys.exit(1 if missing else 0)
PY
}

find_python_for_modules() {
  local modules_csv="$1"
  local candidates=(".venv/bin/python" "python3")

  for candidate in "${candidates[@]}"; do
    if [[ "$candidate" == ".venv/bin/python" && ! -x "$candidate" ]]; then
      continue
    fi
    if REQUIRED_MODULES="$modules_csv" python_supports_modules "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! BUILD_PYTHON="$(find_python_for_modules "openpyxl,PyInstaller")"; then
  echo "Nao foi encontrado um interpretador Python com openpyxl e PyInstaller." >&2
  echo "Instale as dependencias com: python3 -m pip install -r requirements.txt" >&2
  exit 1
fi

if ! ICON_PYTHON="$(find_python_for_modules "PIL")"; then
  echo "Nao foi encontrado um interpretador Python com Pillow (PIL)." >&2
  echo "Instale as dependencias com: python3 -m pip install -r requirements.txt" >&2
  exit 1
fi

if [[ "$RUN_TESTS" != "0" ]]; then
  echo "Executando testes antes do build..."
  "$BUILD_PYTHON" -m unittest tests.test_services tests.test_storage tests.test_resources tests.test_display tests.test_release_files
fi

"$ICON_PYTHON" scripts/generate_icons.py
"$BUILD_PYTHON" -m PyInstaller --noconfirm --clean documentos_empresa_app.spec

APP_VERSION="$("$BUILD_PYTHON" -c "from documentos_empresa_app import __version__; print(__version__)")"
ARCH_NAME="$(uname -m)"
mkdir -p "$DIST_RELEASE_DIR"

case "$(uname -s)" in
  Darwin)
    RELEASE_ARCHIVE="$DIST_RELEASE_DIR/DocFLow-macos-${ARCH_NAME}-v${APP_VERSION}.tar.gz"
    ;;
  Linux)
    RELEASE_ARCHIVE="$DIST_RELEASE_DIR/DocFLow-linux-${ARCH_NAME}-v${APP_VERSION}.tar.gz"
    ;;
  *)
    RELEASE_ARCHIVE="$DIST_RELEASE_DIR/DocFLow-v${APP_VERSION}.tar.gz"
    ;;
esac

rm -f "$RELEASE_ARCHIVE"
tar -czf "$RELEASE_ARCHIVE" -C "$ROOT_DIR/dist" "DocFLow"

echo
echo "Build concluido em: $DIST_DIR"
echo "Arquivo de distribuicao: $RELEASE_ARCHIVE"
case "$(uname -s)" in
  Darwin)
    echo "Icone de empacotamento: assets/icons/icon.icns"
    ;;
  Linux)
    echo "Icone da interface/desktop integration: assets/icons/icon.png"
    ;;
esac
