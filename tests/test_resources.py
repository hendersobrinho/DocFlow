from __future__ import annotations

from pathlib import Path
import unittest

from documentos_empresa_app.utils.resources import (
    get_icons_directory,
    get_master_icon_path,
    get_packaging_icon_filename,
    get_packaging_icon_path,
    get_window_icon_filenames,
)


class ResourceHelperTests(unittest.TestCase):
    def test_get_icons_directory_uses_assets_icons_structure(self) -> None:
        base_path = Path("/tmp/gdocs")
        self.assertEqual(get_icons_directory(base_path), base_path / "assets" / "icons")

    def test_get_master_icon_path_uses_svg_in_icons_directory(self) -> None:
        base_path = Path("/tmp/gdocs")
        self.assertEqual(get_master_icon_path(base_path), base_path / "assets" / "icons" / "icon.svg")

    def test_packaging_icon_filename_changes_by_platform(self) -> None:
        self.assertEqual(get_packaging_icon_filename("win32"), "icon.ico")
        self.assertEqual(get_packaging_icon_filename("darwin"), "icon.icns")
        self.assertEqual(get_packaging_icon_filename("linux"), "icon.png")

    def test_packaging_icon_path_uses_platform_specific_filename(self) -> None:
        base_path = Path("/tmp/gdocs")
        self.assertEqual(
            get_packaging_icon_path(base_path, "win32"),
            base_path / "assets" / "icons" / "icon.ico",
        )

    def test_window_icon_filenames_prefer_png_on_non_windows(self) -> None:
        self.assertEqual(get_window_icon_filenames("linux"), ("icon.png", "icon.ico"))
        self.assertEqual(get_window_icon_filenames("darwin"), ("icon.png", "icon.ico"))


if __name__ == "__main__":
    unittest.main()
