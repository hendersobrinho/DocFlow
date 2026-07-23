from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from documentos_empresa_app import __version__


ROOT_DIR = Path(__file__).resolve().parents[1]
README_PATH = ROOT_DIR / "README.md"
INSTALLER_PATH = ROOT_DIR / "assets" / "installer" / "DocFLow.iss"
GENERATE_ICONS_SCRIPT_PATH = ROOT_DIR / "scripts" / "generate_icons.py"


def load_generate_icons_module():
    spec = importlib.util.spec_from_file_location("generate_icons_script", GENERATE_ICONS_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar o script: {GENERATE_ICONS_SCRIPT_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATE_ICONS_MODULE = load_generate_icons_module()


class ReleaseFileTests(unittest.TestCase):
    def test_readme_version_matches_package_version(self) -> None:
        readme_text = README_PATH.read_text(encoding="utf-8")
        self.assertIn(f"Versao atual: `{__version__}`", readme_text)

    def test_installer_version_matches_package_version(self) -> None:
        installer_text = INSTALLER_PATH.read_text(encoding="utf-8")
        match = re.search(r'#define AppVersion "([^"]+)"', installer_text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)

    def test_installer_uses_docflow_branding(self) -> None:
        installer_text = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn('#define AppName "DocFLow"', installer_text)
        self.assertIn('#define AppExeName "DocFLow.exe"', installer_text)

    def test_simple_svg_fallback_renders_master_icon(self) -> None:
        image = GENERATE_ICONS_MODULE.render_simple_svg(GENERATE_ICONS_MODULE.MASTER_ICON_PATH)

        self.assertEqual(image.size, (GENERATE_ICONS_MODULE.OUTPUT_SIZE, GENERATE_ICONS_MODULE.OUTPUT_SIZE))
        self.assertIsNotNone(image.getchannel("A").getbbox())

    def test_optional_icns_failure_does_not_block_non_macos_builds(self) -> None:
        output = io.StringIO()
        with patch.object(GENERATE_ICONS_MODULE, "save_icns", side_effect=OSError("icns indisponivel")):
            with contextlib.redirect_stdout(output):
                generated = GENERATE_ICONS_MODULE.save_optional_icns(
                    object(),
                    Path("icon.icns"),
                    platform="win32",
                )

        self.assertFalse(generated)
        self.assertIn("icon.icns", output.getvalue())
        self.assertIn("fora do macOS", output.getvalue())

    def test_optional_icns_failure_still_blocks_macos_builds(self) -> None:
        with patch.object(GENERATE_ICONS_MODULE, "save_icns", side_effect=OSError("icns indisponivel")):
            with self.assertRaisesRegex(RuntimeError, "icon.icns necessario para o build do macOS"):
                GENERATE_ICONS_MODULE.save_optional_icns(
                    object(),
                    Path("icon.icns"),
                    platform="darwin",
                )

    def test_generate_icons_uses_larger_canvas_for_windows_ico(self) -> None:
        source_image = object()
        default_normalized_image = object()
        windows_normalized_image = object()

        with patch.object(GENERATE_ICONS_MODULE, "load_svg_as_image", return_value=source_image):
            with patch.object(
                GENERATE_ICONS_MODULE,
                "normalize_icon_canvas",
                side_effect=[default_normalized_image, windows_normalized_image],
            ) as normalize_mock:
                with patch.object(GENERATE_ICONS_MODULE, "save_png") as save_png_mock:
                    with patch.object(GENERATE_ICONS_MODULE, "save_ico") as save_ico_mock:
                        with patch.object(GENERATE_ICONS_MODULE, "save_optional_icns", return_value=False) as save_icns_mock:
                            generated_files = GENERATE_ICONS_MODULE.generate_icons(platform="win32")

        self.assertEqual(normalize_mock.call_count, 2)
        self.assertEqual(normalize_mock.call_args_list[0].args, (source_image,))
        self.assertEqual(normalize_mock.call_args_list[0].kwargs, {})
        self.assertEqual(normalize_mock.call_args_list[1].args, (source_image,))
        self.assertEqual(
            normalize_mock.call_args_list[1].kwargs,
            {"inner_size_ratio": GENERATE_ICONS_MODULE.WINDOWS_ICON_INNER_SIZE_RATIO},
        )
        save_png_mock.assert_called_once_with(default_normalized_image, GENERATE_ICONS_MODULE.PNG_ICON_PATH)
        save_ico_mock.assert_called_once_with(windows_normalized_image, GENERATE_ICONS_MODULE.ICO_ICON_PATH)
        save_icns_mock.assert_called_once_with(
            default_normalized_image,
            GENERATE_ICONS_MODULE.ICNS_ICON_PATH,
            platform="win32",
        )
        self.assertEqual(
            generated_files,
            [
                GENERATE_ICONS_MODULE.PNG_ICON_PATH.name,
                GENERATE_ICONS_MODULE.ICO_ICON_PATH.name,
            ],
        )

    def test_normalize_icon_canvas_can_scale_up_source_image(self) -> None:
        class FakeImage:
            def __init__(self, width: int, height: int) -> None:
                self.width = width
                self.height = height

            def getchannel(self, _name: str):
                return self

            def getbbox(self):
                return (0, 0, self.width, self.height)

            def crop(self, bbox):
                return FakeImage(bbox[2] - bbox[0], bbox[3] - bbox[1])

            def resize(self, size, _resampling):
                return FakeImage(*size)

        class FakeCanvas:
            def __init__(self, size) -> None:
                self.size = size
                self.pasted_image = None
                self.paste_offset = None

            def paste(self, image, offset, _mask) -> None:
                self.pasted_image = image
                self.paste_offset = offset

        class FakeImageModule:
            class Resampling:
                LANCZOS = object()

            @staticmethod
            def new(_mode, size, _color):
                return FakeCanvas(size)

        with patch.object(GENERATE_ICONS_MODULE, "get_pillow_image_module", return_value=FakeImageModule):
            canvas = GENERATE_ICONS_MODULE.normalize_icon_canvas(
                FakeImage(200, 100),
                inner_size_ratio=0.9,
            )

        self.assertEqual(canvas.size, (GENERATE_ICONS_MODULE.OUTPUT_SIZE, GENERATE_ICONS_MODULE.OUTPUT_SIZE))
        self.assertIsNotNone(canvas.pasted_image)
        self.assertGreater(canvas.pasted_image.width, 200)
        self.assertGreater(canvas.pasted_image.height, 100)


if __name__ == "__main__":
    unittest.main()
