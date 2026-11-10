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
# Versao para 16 a 48 px: a folha maior e mais grossa, senao some e o D fica todo branco.
SMALL_ICON_PATH = ICONS_DIR / "icon-pequeno.svg"
SMALL_ICO_SIZES = (16, 24, 32, 48)
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


def render_svg_with_qt(svg_path: Path, size: int = OUTPUT_SIZE) -> Image.Image | None:
    """Desenha o SVG com o QtSvg (vem com o PySide6, que o build ja instala). Entende tudo do
    SVG, inclusive os arcos dos cantos da folha - o desenhador simples abaixo nao entende."""
    try:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QByteArray, Qt
        from PySide6.QtGui import QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer
    except ImportError:
        return None
    _app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(QByteArray(svg_path.read_bytes()))
    if not renderer.isValid():
        return None
    qimage = QImage(size, size, QImage.Format.Format_ARGB32)
    qimage.fill(Qt.GlobalColor.transparent)
    painter = QPainter(qimage)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    image_module = get_pillow_image_module()
    data = qimage.bits().tobytes()
    return image_module.frombuffer("RGBA", (size, size), data, "raw", "BGRA", 0, 1).copy()


def load_svg_as_image(svg_path: Path) -> Image.Image:
    image_module = get_pillow_image_module()
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        rendered = render_svg_with_qt(svg_path)
        if rendered is not None:
            return rendered
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


_IDENTITY_MATRIX: tuple[float, float, float, float, float, float] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_TRANSFORM_FUNC_PATTERN = re.compile(r"(\w+)\(([^)]*)\)")


def _multiply_matrices(
    outer: tuple[float, float, float, float, float, float],
    inner: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a1, b1, c1, d1, e1, f1 = outer
    a2, b2, c2, d2, e2, f2 = inner
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _parse_transform(transform_str: str | None) -> tuple[float, float, float, float, float, float]:
    """Suporta apenas translate()/scale(), unicas funcoes usadas no icone mestre."""
    matrix = _IDENTITY_MATRIX
    if not transform_str:
        return matrix

    for name, args_str in _TRANSFORM_FUNC_PATTERN.findall(transform_str):
        args = [float(value) for value in re.split(r"[\s,]+", args_str.strip()) if value]
        if name == "translate":
            tx = args[0] if args else 0.0
            ty = args[1] if len(args) > 1 else 0.0
            local_matrix = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == "scale":
            sx = args[0] if args else 1.0
            sy = args[1] if len(args) > 1 else sx
            local_matrix = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        else:
            continue
        matrix = _multiply_matrices(matrix, local_matrix)

    return matrix


def _get_href(element: ElementTree.Element) -> str | None:
    href = element.attrib.get("href")
    if href:
        return href
    for key, value in element.attrib.items():
        if key.endswith("}href"):
            return value
    return None


def _average_gradient_color(gradient_element: ElementTree.Element) -> str:
    from PIL import ImageColor

    stop_colors = [
        stop.attrib["stop-color"]
        for stop in gradient_element
        if _strip_svg_namespace(stop.tag) == "stop" and stop.attrib.get("stop-color")
    ]
    if not stop_colors:
        return "#000000"

    rgb_values = [ImageColor.getrgb(color) for color in stop_colors]
    averaged = tuple(round(sum(channel) / len(channel)) for channel in zip(*rgb_values))
    return "#%02x%02x%02x" % averaged


def _collect_defs(
    root: ElementTree.Element,
) -> tuple[dict[str, ElementTree.Element], dict[str, str]]:
    """Indexa por id: elementos reutilizaveis (para <use href="#id">) e gradientes
    (reduzidos a uma cor solida media, ja que este renderer nao suporta degrade)."""
    elements_by_id: dict[str, ElementTree.Element] = {}
    gradients_by_id: dict[str, str] = {}
    for element in root.iter():
        element_id = element.attrib.get("id")
        if not element_id:
            continue
        if _strip_svg_namespace(element.tag) in ("linearGradient", "radialGradient"):
            gradients_by_id[element_id] = _average_gradient_color(element)
        else:
            elements_by_id[element_id] = element
    return elements_by_id, gradients_by_id


def _resolve_fill(raw_fill: str | None, gradients_by_id: dict[str, str]) -> str | None:
    color = _parse_color(raw_fill)
    if color is None:
        return None
    match = re.fullmatch(r"url\(#([^)]+)\)", color)
    if match:
        return gradients_by_id.get(match.group(1))
    return color


def render_simple_svg(svg_path: Path) -> Image.Image:
    image_module = get_pillow_image_module()
    from PIL import ImageDraw

    root = ElementTree.fromstring(svg_path.read_text(encoding="utf-8"))
    min_x, min_y, viewbox_width, viewbox_height = _parse_viewbox(root)
    scale = min(OUTPUT_SIZE / viewbox_width, OUTPUT_SIZE / viewbox_height)
    image = image_module.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    elements_by_id, gradients_by_id = _collect_defs(root)

    def transform(
        matrix: tuple[float, float, float, float, float, float],
        point: tuple[float, float],
    ) -> tuple[float, float]:
        a, b, c, d, e, f = matrix
        x, y = point
        world_x, world_y = a * x + c * y + e, b * x + d * y + f
        return (world_x - min_x) * scale, (world_y - min_y) * scale

    def draw_shape(
        element: ElementTree.Element,
        matrix: tuple[float, float, float, float, float, float],
    ) -> None:
        tag_name = _strip_svg_namespace(element.tag)
        if tag_name == "rect":
            fill = _resolve_fill(element.attrib.get("fill"), gradients_by_id)
            if not fill:
                return
            x = _parse_float(element.attrib.get("x"))
            y = _parse_float(element.attrib.get("y"))
            width = _parse_float(element.attrib.get("width"))
            height = _parse_float(element.attrib.get("height"))
            radius = _parse_float(element.attrib.get("rx"))
            corner_a = transform(matrix, (x, y))
            corner_b = transform(matrix, (x + width, y + height))
            draw.rounded_rectangle(
                [
                    (min(corner_a[0], corner_b[0]), min(corner_a[1], corner_b[1])),
                    (max(corner_a[0], corner_b[0]), max(corner_a[1], corner_b[1])),
                ],
                radius=radius * scale,
                fill=fill,
            )
            return

        if tag_name != "path":
            return

        paths = _parse_simple_svg_path(element.attrib.get("d", ""))
        fill = _resolve_fill(element.attrib.get("fill"), gradients_by_id)
        stroke = _resolve_fill(element.attrib.get("stroke"), gradients_by_id)
        stroke_width = max(1, round(_parse_float(element.attrib.get("stroke-width"), 1.0) * scale))
        linecap = element.attrib.get("stroke-linecap", "").strip().lower()

        for path in paths:
            transformed_path = [transform(matrix, point) for point in path]
            if fill and len(transformed_path) >= 3:
                draw.polygon(transformed_path, fill=fill)
            if stroke and len(transformed_path) >= 2:
                draw.line(transformed_path, fill=stroke, width=stroke_width, joint="curve")
                if linecap == "round":
                    radius = stroke_width / 2
                    for x, y in (transformed_path[0], transformed_path[-1]):
                        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=stroke)

    def walk(
        parent: ElementTree.Element,
        matrix: tuple[float, float, float, float, float, float],
    ) -> None:
        for child in parent:
            tag_name = _strip_svg_namespace(child.tag)
            if tag_name == "defs":
                continue

            local_matrix = _multiply_matrices(matrix, _parse_transform(child.attrib.get("transform")))

            if tag_name == "use":
                href = _get_href(child)
                referenced = elements_by_id.get(href.lstrip("#")) if href else None
                if referenced is not None:
                    use_offset = (
                        _parse_float(child.attrib.get("x")),
                        _parse_float(child.attrib.get("y")),
                    )
                    use_matrix = _multiply_matrices(local_matrix, (1.0, 0.0, 0.0, 1.0, *use_offset))
                    draw_shape(referenced, use_matrix)
                    walk(referenced, use_matrix)
                continue

            draw_shape(child, local_matrix)
            walk(child, local_matrix)

    walk(root, _IDENTITY_MATRIX)
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


def small_ico_frames() -> dict[int, Image.Image]:
    """Os tamanhos pequenos desenhados direto no tamanho final, a partir do icon-pequeno.svg."""
    if not SMALL_ICON_PATH.exists():
        return {}
    frames = {}
    for size in SMALL_ICO_SIZES:
        frame = render_svg_with_qt(SMALL_ICON_PATH, size)
        if frame is None:
            return {}
        frames[size] = frame
    return frames


def save_ico(image: Image.Image, destination: Path) -> None:
    image_module = get_pillow_image_module()
    small = small_ico_frames()
    frames = [
        small.get(width) or image.resize((width, height), image_module.Resampling.LANCZOS)
        for width, height in ICO_SIZES
    ]
    largest = frames[-1]
    largest.save(destination, format="ICO", sizes=ICO_SIZES, append_images=frames[:-1])


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
