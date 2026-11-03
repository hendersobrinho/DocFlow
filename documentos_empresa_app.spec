# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
ICONS_DIR = ROOT_DIR / "assets" / "icons"
BUILD_PLATFORM = sys.platform
APP_NAME = "DocFLow"

try:
    import mcp  # noqa: F401  (sem ele o DocFLow-MCP.exe sai quebrado)
except ImportError as exc:
    raise SystemExit("Falta o pacote mcp: pip install -r requirements-mcp.txt") from exc


def get_build_icon_path() -> Path | None:
    if BUILD_PLATFORM.startswith("win"):
        return ICONS_DIR / "icon.ico"
    if BUILD_PLATFORM == "darwin":
        return ICONS_DIR / "icon.icns"
    return None


icon_file = get_build_icon_path()
icon_datas = [(str(path), "assets/icons") for path in sorted(ICONS_DIR.iterdir()) if path.is_file()]
# Identidade visual: logos/simbolo (assets/brand) e as fontes da marca (assets/fonts).
for _folder in ("brand", "fonts"):
    _dir = ROOT_DIR / "assets" / _folder
    icon_datas += [(str(path), f"assets/{_folder}") for path in sorted(_dir.iterdir()) if path.is_file()]


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=icon_datas,
    # O psycopg carrega a implementacao binaria (com a libpq embutida) dinamicamente.
    hiddenimports=["psycopg_binary"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# DocFLow-MCP.exe: o servidor MCP para o Claude Desktop, na mesma pasta do DocFLow.exe
# (console, porque conversa com o Claude por stdin/stdout).
mcp_a = Analysis(
    [str(ROOT_DIR / "docflow_mcp" / "__main__.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=["psycopg_binary", "docflow_mcp.server"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
mcp_pyz = PYZ(mcp_a.pure)
mcp_exe = EXE(
    mcp_pyz,
    mcp_a.scripts,
    [],
    exclude_binaries=True,
    name=f"{APP_NAME}-MCP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file else None,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    mcp_exe,
    mcp_a.binaries,
    mcp_a.zipfiles,
    mcp_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
