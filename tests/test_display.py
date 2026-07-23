from __future__ import annotations

import unittest

from documentos_empresa_app.utils.display import (
    ScreenBounds,
    _parse_xrandr_geometry,
    _select_screen_bounds,
)


class DisplayHelperTests(unittest.TestCase):
    def test_parse_xrandr_primary_line(self) -> None:
        line = "HDMI-1 connected primary 1920x1080+1920+0 (normal left inverted right x axis y axis)"
        bounds = _parse_xrandr_geometry(line)

        self.assertEqual(bounds, ScreenBounds(x=1920, y=0, width=1920, height=1080))

    def test_parse_xrandr_returns_none_without_geometry(self) -> None:
        line = "HDMI-1 connected primary"
        bounds = _parse_xrandr_geometry(line)

        self.assertIsNone(bounds)

    def test_select_screen_uses_pointer_monitor_first(self) -> None:
        left_screen = ScreenBounds(x=0, y=0, width=1920, height=1080)
        right_screen = ScreenBounds(x=1920, y=0, width=1920, height=1080)

        selected = _select_screen_bounds(
            [left_screen, right_screen],
            left_screen,
            pointer_x=2200,
            pointer_y=500,
        )

        self.assertEqual(selected, right_screen)

    def test_select_screen_falls_back_to_primary(self) -> None:
        left_screen = ScreenBounds(x=0, y=0, width=1920, height=1080)
        right_screen = ScreenBounds(x=1920, y=0, width=1920, height=1080)

        selected = _select_screen_bounds(
            [left_screen, right_screen],
            left_screen,
            pointer_x=5000,
            pointer_y=500,
        )

        self.assertEqual(selected, left_screen)


if __name__ == "__main__":
    unittest.main()
