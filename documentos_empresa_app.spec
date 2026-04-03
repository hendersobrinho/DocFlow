# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


ROOT_DIR = Path.cwd()
ICONS_DIR = ROOT_DIR / "assets" / "icons"
BUILD_PLATFORM = sys.platform


def get_build_icon_path() -> Path | None:
    if BUILD_PLATFORM.startswith("win"):
        return ICONS_DIR / "icon.ico"
    if BUILD_PLATFORM == "darwin":
        return ICONS_DIR / "icon.icns"
    return None


icon_file = get_build_icon_path()
icon_datas = [(str(path), "assets/icons") for path in sorted(ICONS_DIR.iterdir()) if path.is_file()]


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=icon_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="G-docs",
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
    strip=False,
    upx=True,
    upx_exclude=[],
    name="G-docs",
)
