from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT_DIR / "assets" / "icons"
MASTER_ICON_PATH = ICONS_DIR / "icon.svg"
PNG_ICON_PATH = ICONS_DIR / "icon.png"
ICO_ICON_PATH = ICONS_DIR / "icon.ico"
ICNS_ICON_PATH = ICONS_DIR / "icon.icns"
OUTPUT_SIZE = 1024
INNER_SIZE_RATIO = 0.82
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
EMBEDDED_PNG_PATTERN = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)")


def load_svg_as_image(svg_path: Path) -> Image.Image:
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        return extract_embedded_png(svg_path)

    png_bytes = cairosvg.svg2png(
        url=str(svg_path),
        output_width=OUTPUT_SIZE,
        output_height=OUTPUT_SIZE,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def extract_embedded_png(svg_path: Path) -> Image.Image:
    svg_text = svg_path.read_text(encoding="utf-8")
    match = EMBEDDED_PNG_PATTERN.search(svg_text)
    if not match:
        raise RuntimeError(
            "Nao foi possivel renderizar o SVG. Instale 'cairosvg' ou use um icon.svg com PNG embutido."
        )

    png_data = base64.b64decode(re.sub(r"\s+", "", match.group(1)))
    return Image.open(io.BytesIO(png_data)).convert("RGBA")


def normalize_icon_canvas(image: Image.Image) -> Image.Image:
    alpha_channel = image.getchannel("A")
    bounding_box = alpha_channel.getbbox() or image.getbbox()
    if not bounding_box:
        raise RuntimeError("O arquivo fonte nao possui area visivel para gerar os icones.")

    cropped_image = image.crop(bounding_box)
    target_size = int(OUTPUT_SIZE * INNER_SIZE_RATIO)
    resized_image = cropped_image.copy()
    resized_image.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
    offset_x = (OUTPUT_SIZE - resized_image.width) // 2
    offset_y = (OUTPUT_SIZE - resized_image.height) // 2
    canvas.paste(resized_image, (offset_x, offset_y), resized_image)
    return canvas


def save_png(image: Image.Image, destination: Path) -> None:
    image.save(destination, format="PNG")


def save_ico(image: Image.Image, destination: Path) -> None:
    image.save(destination, format="ICO", sizes=ICO_SIZES)


def save_icns(image: Image.Image, destination: Path) -> None:
    image.save(destination, format="ICNS")


def generate_icons() -> None:
    if not MASTER_ICON_PATH.exists():
        raise FileNotFoundError(f"Arquivo mestre nao encontrado: {MASTER_ICON_PATH}")

    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    normalized_image = normalize_icon_canvas(load_svg_as_image(MASTER_ICON_PATH))
    save_png(normalized_image, PNG_ICON_PATH)
    save_ico(normalized_image, ICO_ICON_PATH)
    save_icns(normalized_image, ICNS_ICON_PATH)


def main() -> None:
    generate_icons()
    print(f"Icones atualizados em: {ICONS_DIR}")
    print(f"- Mestre: {MASTER_ICON_PATH.name}")
    print(f"- Linux/interface: {PNG_ICON_PATH.name}")
    print(f"- Windows: {ICO_ICON_PATH.name}")
    print(f"- macOS: {ICNS_ICON_PATH.name}")


if __name__ == "__main__":
    main()
