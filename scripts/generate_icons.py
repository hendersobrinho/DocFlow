from __future__ import annotations

import base64
import io
import re
import sys
from xml.etree import ElementTree
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT_DIR / "assets" / "icons"
MASTER_ICON_PATH = ICONS_DIR / "icon.svg"
PNG_ICON_PATH = ICONS_DIR / "icon.png"
ICO_ICON_PATH = ICONS_DIR / "icon.ico"
ICNS_ICON_PATH = ICONS_DIR / "icon.icns"
OUTPUT_SIZE = 1024
DEFAULT_INNER_SIZE_RATIO = 0.82
WINDOWS_ICON_INNER_SIZE_RATIO = 0.90
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
EMBEDDED_PNG_PATTERN = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)")
SVG_PATH_TOKEN_PATTERN = re.compile(r"[MLHVCZmlhvcz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
SVG_NAMESPACE = "{http://www.w3.org/2000/svg}"


def get_pillow_image_module():
    from PIL import Image

    return Image


def load_svg_as_image(svg_path: Path) -> Image.Image:
    image_module = get_pillow_image_module()
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        try:
            return extract_embedded_png(svg_path)
        except RuntimeError:
            return render_simple_svg(svg_path)

    png_bytes = cairosvg.svg2png(
        url=str(svg_path),
        output_width=OUTPUT_SIZE,
        output_height=OUTPUT_SIZE,
    )
    return image_module.open(io.BytesIO(png_bytes)).convert("RGBA")


def extract_embedded_png(svg_path: Path) -> Image.Image:
    image_module = get_pillow_image_module()
    svg_text = svg_path.read_text(encoding="utf-8")
    match = EMBEDDED_PNG_PATTERN.search(svg_text)
    if not match:
        raise RuntimeError(
            "Nao foi possivel renderizar o SVG. Instale 'cairosvg' ou use um icon.svg com PNG embutido."
        )

    png_data = base64.b64decode(re.sub(r"\s+", "", match.group(1)))
    return image_module.open(io.BytesIO(png_data)).convert("RGBA")


def _strip_svg_namespace(tag_name: str) -> str:
    return tag_name.removeprefix(SVG_NAMESPACE)


def _parse_color(raw_color: str | None) -> str | None:
    if raw_color is None:
        return None
    normalized = raw_color.strip()
    if not normalized or normalized.lower() == "none":
        return None
    return normalized


def _parse_float(raw_value: str | None, default: float = 0.0) -> float:
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def _parse_viewbox(root: ElementTree.Element) -> tuple[float, float, float, float]:
    viewbox = root.attrib.get("viewBox")
    if viewbox:
        values = [float(value) for value in re.split(r"[\s,]+", viewbox.strip()) if value]
        if len(values) == 4:
            return values[0], values[1], values[2], values[3]

    width = _parse_float(root.attrib.get("width"), OUTPUT_SIZE)
    height = _parse_float(root.attrib.get("height"), OUTPUT_SIZE)
    return 0.0, 0.0, width, height


def _cubic_point(
    start: tuple[float, float],
    control_a: tuple[float, float],
    control_b: tuple[float, float],
    end: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    inv_t = 1.0 - t
    x = (
        inv_t**3 * start[0]
        + 3 * inv_t**2 * t * control_a[0]
        + 3 * inv_t * t**2 * control_b[0]
        + t**3 * end[0]
    )
    y = (
        inv_t**3 * start[1]
        + 3 * inv_t**2 * t * control_a[1]
        + 3 * inv_t * t**2 * control_b[1]
        + t**3 * end[1]
    )
    return x, y


def _parse_simple_svg_path(path_data: str) -> list[list[tuple[float, float]]]:
    tokens = SVG_PATH_TOKEN_PATTERN.findall(path_data)
    paths: list[list[tuple[float, float]]] = []
    current_path: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    path_start = (0.0, 0.0)
    command = ""
    index = 0

    def read_number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def has_number() -> bool:
        return index < len(tokens) and not re.fullmatch(r"[MLHVCZmlhvcz]", tokens[index])

    while index < len(tokens):
        token = tokens[index]
        if re.fullmatch(r"[MLHVCZmlhvcz]", token):
            command = token
            index += 1

        is_relative = command.islower()
        normalized_command = command.upper()

        if normalized_command == "M":
            x = read_number()
            y = read_number()
            if is_relative:
                x += current[0]
                y += current[1]
            current = (x, y)
            path_start = current
            current_path = [current]
            paths.append(current_path)
            command = "l" if is_relative else "L"
            continue

        if normalized_command == "L":
            while has_number():
                x = read_number()
                y = read_number()
                if is_relative:
                    x += current[0]
                    y += current[1]
                current = (x, y)
                current_path.append(current)
            continue

        if normalized_command == "H":
            while has_number():
                x = read_number()
                if is_relative:
                    x += current[0]
                current = (x, current[1])
                current_path.append(current)
            continue

        if normalized_command == "V":
            while has_number():
                y = read_number()
                if is_relative:
                    y += current[1]
                current = (current[0], y)
                current_path.append(current)
            continue

        if normalized_command == "C":
            while has_number():
                control_a = (read_number(), read_number())
                control_b = (read_number(), read_number())
                end = (read_number(), read_number())
                if is_relative:
                    control_a = (control_a[0] + current[0], control_a[1] + current[1])
                    control_b = (control_b[0] + current[0], control_b[1] + current[1])
                    end = (end[0] + current[0], end[1] + current[1])
                for step in range(1, 25):
                    current_path.append(_cubic_point(current, control_a, control_b, end, step / 24))
                current = end
            continue

        if normalized_command == "Z":
            current_path.append(path_start)
            current = path_start
            command = ""
            continue

        raise RuntimeError(f"Comando SVG nao suportado no icone: {command}")

    return paths


def render_simple_svg(svg_path: Path) -> Image.Image:
    image_module = get_pillow_image_module()
    from PIL import ImageDraw

    root = ElementTree.fromstring(svg_path.read_text(encoding="utf-8"))
    min_x, min_y, viewbox_width, viewbox_height = _parse_viewbox(root)
    scale = min(OUTPUT_SIZE / viewbox_width, OUTPUT_SIZE / viewbox_height)
    image = image_module.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def transform(point: tuple[float, float]) -> tuple[float, float]:
        return (point[0] - min_x) * scale, (point[1] - min_y) * scale

    for element in root:
        tag_name = _strip_svg_namespace(element.tag)
        if tag_name == "rect":
            fill = _parse_color(element.attrib.get("fill"))
            if not fill:
                continue
            x = _parse_float(element.attrib.get("x"))
            y = _parse_float(element.attrib.get("y"))
            width = _parse_float(element.attrib.get("width"))
            height = _parse_float(element.attrib.get("height"))
            radius = _parse_float(element.attrib.get("rx"))
            draw.rounded_rectangle(
                [
                    transform((x, y)),
                    transform((x + width, y + height)),
                ],
                radius=radius * scale,
                fill=fill,
            )
            continue

        if tag_name != "path":
            continue

        paths = _parse_simple_svg_path(element.attrib.get("d", ""))
        fill = _parse_color(element.attrib.get("fill"))
        stroke = _parse_color(element.attrib.get("stroke"))
        stroke_width = max(1, round(_parse_float(element.attrib.get("stroke-width"), 1.0) * scale))
        linecap = element.attrib.get("stroke-linecap", "").strip().lower()

        for path in paths:
            transformed_path = [transform(point) for point in path]
            if fill and len(transformed_path) >= 3:
                draw.polygon(transformed_path, fill=fill)
            if stroke and len(transformed_path) >= 2:
                draw.line(transformed_path, fill=stroke, width=stroke_width, joint="curve")
                if linecap == "round":
                    radius = stroke_width / 2
                    for x, y in (transformed_path[0], transformed_path[-1]):
                        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=stroke)

    return image


def normalize_icon_canvas(
    image: Image.Image,
    inner_size_ratio: float = DEFAULT_INNER_SIZE_RATIO,
) -> Image.Image:
    image_module = get_pillow_image_module()
    alpha_channel = image.getchannel("A")
    bounding_box = alpha_channel.getbbox() or image.getbbox()
    if not bounding_box:
        raise RuntimeError("O arquivo fonte nao possui area visivel para gerar os icones.")

    cropped_image = image.crop(bounding_box)
    target_size = int(OUTPUT_SIZE * inner_size_ratio)
    scale_factor = min(target_size / cropped_image.width, target_size / cropped_image.height)
    resized_size = (
        max(1, round(cropped_image.width * scale_factor)),
        max(1, round(cropped_image.height * scale_factor)),
    )
    resized_image = cropped_image.resize(resized_size, image_module.Resampling.LANCZOS)

    canvas = image_module.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
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


def save_optional_icns(image: Image.Image, destination: Path, platform: str | None = None) -> bool:
    current_platform = platform or sys.platform
    try:
        save_icns(image, destination)
    except Exception as exc:
        if current_platform == "darwin":
            raise RuntimeError(
                "Nao foi possivel gerar o icon.icns necessario para o build do macOS."
            ) from exc

        print(
            "Aviso: nao foi possivel gerar icon.icns neste ambiente; "
            "o build segue normalmente fora do macOS."
        )
        return False

    return True


def generate_icons(platform: str | None = None) -> list[str]:
    if not MASTER_ICON_PATH.exists():
        raise FileNotFoundError(f"Arquivo mestre nao encontrado: {MASTER_ICON_PATH}")

    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    source_image = load_svg_as_image(MASTER_ICON_PATH)
    default_normalized_image = normalize_icon_canvas(source_image)
    windows_normalized_image = normalize_icon_canvas(
        source_image,
        inner_size_ratio=WINDOWS_ICON_INNER_SIZE_RATIO,
    )
    generated_files: list[str] = []

    save_png(default_normalized_image, PNG_ICON_PATH)
    generated_files.append(PNG_ICON_PATH.name)
    save_ico(windows_normalized_image, ICO_ICON_PATH)
    generated_files.append(ICO_ICON_PATH.name)

    if save_optional_icns(default_normalized_image, ICNS_ICON_PATH, platform=platform):
        generated_files.append(ICNS_ICON_PATH.name)

    return generated_files


def main() -> None:
    generated_files = generate_icons()
    print(f"Icones atualizados em: {ICONS_DIR}")
    print(f"- Mestre: {MASTER_ICON_PATH.name}")
    print(f"- Linux/interface: {PNG_ICON_PATH.name}")
    print(f"- Windows: {ICO_ICON_PATH.name}")
    if ICNS_ICON_PATH.name in generated_files:
        print(f"- macOS: {ICNS_ICON_PATH.name}")
    else:
        print(f"- macOS: {ICNS_ICON_PATH.name} (mantido sem regenerar neste ambiente)")


if __name__ == "__main__":
    main()
