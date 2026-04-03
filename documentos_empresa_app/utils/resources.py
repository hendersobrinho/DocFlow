from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk


ASSETS_DIRNAME = "assets"
ICONS_DIRNAME = "icons"
MASTER_ICON_FILENAME = "icon.svg"
WINDOWS_ICON_FILENAME = "icon.ico"
MACOS_ICON_FILENAME = "icon.icns"
LINUX_ICON_FILENAME = "icon.png"


def get_runtime_base_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def get_executable_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return get_runtime_base_path()


def _normalize_platform_name(platform_name: str | None = None) -> str:
    return platform_name or sys.platform


def get_icons_directory(base_path: Path | None = None) -> Path:
    root_path = base_path or get_runtime_base_path()
    return root_path / ASSETS_DIRNAME / ICONS_DIRNAME


def get_master_icon_path(base_path: Path | None = None) -> Path:
    return get_icons_directory(base_path) / MASTER_ICON_FILENAME


def get_packaging_icon_filename(platform_name: str | None = None) -> str:
    normalized_platform = _normalize_platform_name(platform_name)
    if normalized_platform.startswith("win"):
        return WINDOWS_ICON_FILENAME
    if normalized_platform == "darwin":
        return MACOS_ICON_FILENAME
    return LINUX_ICON_FILENAME


def get_packaging_icon_path(base_path: Path | None = None, platform_name: str | None = None) -> Path:
    return get_icons_directory(base_path) / get_packaging_icon_filename(platform_name)


def get_window_icon_filenames(platform_name: str | None = None) -> tuple[str, ...]:
    normalized_platform = _normalize_platform_name(platform_name)
    if normalized_platform.startswith("win"):
        return (WINDOWS_ICON_FILENAME, LINUX_ICON_FILENAME)
    if normalized_platform == "darwin":
        return (LINUX_ICON_FILENAME, WINDOWS_ICON_FILENAME)
    return (LINUX_ICON_FILENAME, WINDOWS_ICON_FILENAME)


def iter_icon_candidates(platform_name: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    for root_path in (get_runtime_base_path(), get_executable_directory()):
        icons_directory = get_icons_directory(root_path)
        for icon_filename in get_window_icon_filenames(platform_name):
            candidates.append(icons_directory / icon_filename)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        unique_candidates.append(path)
    return unique_candidates


def apply_window_icon(window: tk.Tk | tk.Toplevel) -> None:
    for path in iter_icon_candidates():
        try:
            if path.suffix.lower() == ".png":
                image = tk.PhotoImage(file=str(path))
                setattr(window, "_app_icon_image", image)
                window.iconphoto(True, image)
                return
            if path.suffix.lower() == ".ico":
                window.iconbitmap(default=str(path))
                return
        except tk.TclError:
            continue
