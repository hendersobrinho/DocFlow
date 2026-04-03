from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
import sys


XRANDR_GEOMETRY_RE = re.compile(r"(?P<width>\d+)x(?P<height>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)")


@dataclass(slots=True)
class ScreenBounds:
    x: int
    y: int
    width: int
    height: int


def get_preferred_screen_bounds(pointer_x: int | None = None, pointer_y: int | None = None) -> ScreenBounds | None:
    if sys.platform.startswith("linux"):
        return _get_linux_preferred_screen_bounds(pointer_x, pointer_y)
    if sys.platform.startswith("win"):
        return _get_windows_primary_screen_bounds()
    if sys.platform == "darwin":
        return _get_macos_primary_screen_bounds()
    return None


def get_primary_screen_bounds() -> ScreenBounds | None:
    if sys.platform.startswith("linux"):
        return _get_linux_primary_screen_bounds()
    if sys.platform.startswith("win"):
        return _get_windows_primary_screen_bounds()
    if sys.platform == "darwin":
        return _get_macos_primary_screen_bounds()
    return None


def _get_linux_preferred_screen_bounds(pointer_x: int | None, pointer_y: int | None) -> ScreenBounds | None:
    screens, primary_screen = _get_linux_gdk_screens(pointer_x, pointer_y)
    if screens:
        return _select_screen_bounds(screens, primary_screen, pointer_x, pointer_y)

    screens, primary_screen = _get_linux_connected_screens()
    return _select_screen_bounds(screens, primary_screen, pointer_x, pointer_y)


def _get_linux_primary_screen_bounds() -> ScreenBounds | None:
    screens, primary_screen = _get_linux_gdk_screens()
    if screens:
        return primary_screen or screens[0]

    screens, primary_screen = _get_linux_connected_screens()
    return primary_screen or (screens[0] if screens else None)


def _get_linux_gdk_screens(
    pointer_x: int | None = None,
    pointer_y: int | None = None,
) -> tuple[list[ScreenBounds], ScreenBounds | None]:
    try:
        import gi

        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk
    except (ImportError, ValueError):
        return [], None

    display = Gdk.Display.get_default()
    if display is None:
        return [], None

    screens: list[ScreenBounds] = []
    primary_screen: ScreenBounds | None = None

    monitor_count = display.get_n_monitors()
    if monitor_count <= 0:
        return [], None

    preferred_monitor = None
    if pointer_x is not None and pointer_y is not None and hasattr(display, "get_monitor_at_point"):
        preferred_monitor = display.get_monitor_at_point(pointer_x, pointer_y)

    for index in range(monitor_count):
        monitor = display.get_monitor(index)
        if monitor is None:
            continue
        geometry = monitor.get_geometry()
        screen = ScreenBounds(
            x=int(geometry.x),
            y=int(geometry.y),
            width=int(geometry.width),
            height=int(geometry.height),
        )
        screens.append(screen)

        if preferred_monitor is not None and monitor == preferred_monitor:
            primary_screen = screen
        elif preferred_monitor is None and hasattr(monitor, "is_primary") and monitor.is_primary():
            primary_screen = screen

    return screens, primary_screen


def _get_linux_connected_screens() -> tuple[list[ScreenBounds], ScreenBounds | None]:
    try:
        output = subprocess.check_output(
            ["xrandr", "--query"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return [], None

    screens: list[ScreenBounds] = []
    primary_screen: ScreenBounds | None = None
    for line in output.splitlines():
        if " connected " not in line:
            continue
        screen = _parse_xrandr_geometry(line)
        if screen is None:
            continue
        screens.append(screen)
        if " connected primary " in line:
            primary_screen = screen

    return screens, primary_screen


def _select_screen_bounds(
    screens: list[ScreenBounds],
    primary_screen: ScreenBounds | None,
    pointer_x: int | None,
    pointer_y: int | None,
) -> ScreenBounds | None:
    if pointer_x is not None and pointer_y is not None:
        for screen in screens:
            if _screen_contains_point(screen, pointer_x, pointer_y):
                return screen
    return primary_screen or (screens[0] if screens else None)


def _screen_contains_point(screen: ScreenBounds, pointer_x: int, pointer_y: int) -> bool:
    return (
        screen.x <= pointer_x < screen.x + screen.width
        and screen.y <= pointer_y < screen.y + screen.height
    )


def _parse_xrandr_geometry(line: str) -> ScreenBounds | None:
    match = XRANDR_GEOMETRY_RE.search(line)
    if not match:
        return None
    return ScreenBounds(
        x=int(match.group("x")),
        y=int(match.group("y")),
        width=int(match.group("width")),
        height=int(match.group("height")),
    )


def _get_windows_primary_screen_bounds() -> ScreenBounds | None:
    try:
        import ctypes
    except ImportError:
        return None

    user32 = ctypes.windll.user32
    width = int(user32.GetSystemMetrics(0))
    height = int(user32.GetSystemMetrics(1))
    if width <= 0 or height <= 0:
        return None
    return ScreenBounds(x=0, y=0, width=width, height=height)


def _get_macos_primary_screen_bounds() -> ScreenBounds | None:
    try:
        from AppKit import NSScreen
    except ImportError:
        return None

    screen = NSScreen.screens()[0] if NSScreen.screens() else None
    if screen is None:
        return None

    frame = screen.visibleFrame()
    return ScreenBounds(
        x=int(frame.origin.x),
        y=int(frame.origin.y),
        width=int(frame.size.width),
        height=int(frame.size.height),
    )
