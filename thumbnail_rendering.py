"""Aspect-preserving artwork fitting for DS Style thumbnail dimensions.

The kernel's 16-bit thumbnail BMPs use pure RGB black (RGB555 word 0) as the
transparent color key. Contained artwork therefore uses a black canvas, and
visible source pixels that quantize to black are lifted to RGB555 value 1 so
that genuine black details are not mistaken for the canvas.
"""

from __future__ import annotations

from PIL import Image


SQUARE_BOX_SIZE = (80, 80)
# Preserve old fill/crop behavior for almost-square sources. More distant aspect
# ratios (portrait box covers or landscape snaps) are contained on the square
# box-art canvas to avoid cutting off their sides or tops.
SQUARE_ASPECT_TOLERANCE = 0.12


def should_fit_art(image: Image.Image, size: tuple[int, int]) -> bool:
    """Return true for distinctly non-square art going to the 80x80 box slot."""
    if size != SQUARE_BOX_SIZE or image.width <= 0 or image.height <= 0:
        return False
    return abs((image.width / image.height) - 1.0) > SQUARE_ASPECT_TOLERANCE


def _avoid_transparent_black(image: Image.Image) -> Image.Image:
    """Adjust visible pixels whose RGB555 value would be 0 to RGB 8,8,8."""
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            # The BMP writer discards RGB's low three bits. Any opaque color
            # with all channels below 8 would consequently become the key color.
            if a >= 128 and (r >> 3) == 0 and (g >> 3) == 0 and (b >> 3) == 0:
                pixels[x, y] = (8, 8, 8, a)
    return image


def fit_image_to_canvas(
    image: Image.Image,
    size: tuple[int, int],
    zoom: float = 1.0,
    x: float = 0.0,
    y: float = 0.0,
) -> Image.Image:
    """Scale proportionally into a transparent canvas using the kernel's black key.

    At default zoom the full art is visible and centered. The existing crop
    editor's zoom/pan controls remain available; zoom above 1 can crop the art.
    The canvas is alpha-transparent in the editor/preview, and the BMP writer
    encodes those pixels as pure black (RGB555 zero) for the kernel.
    """
    target_w, target_h = size
    if target_w <= 0 or target_h <= 0 or image.width <= 0 or image.height <= 0:
        raise ValueError("Image and target dimensions must be positive.")

    source = image.convert("RGBA")
    zoom = max(0.1, min(float(zoom), 5.0))
    x = max(-100.0, min(float(x), 100.0))
    y = max(-100.0, min(float(y), 100.0))
    scale = min(target_w / source.width, target_h / source.height) * zoom
    scaled_w = max(1, round(source.width * scale))
    scaled_h = max(1, round(source.height * scale))
    scaled = source.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
    scaled = _avoid_transparent_black(scaled)

    if scaled_w <= target_w:
        dest_x = round((target_w - scaled_w) / 2 + (x / 100.0) * ((target_w - scaled_w) / 2))
        crop_left = 0
    else:
        crop_left = round((scaled_w - target_w) / 2 + (x / 100.0) * ((scaled_w - target_w) / 2))
        crop_left = max(0, min(scaled_w - target_w, crop_left))
        dest_x = 0

    if scaled_h <= target_h:
        dest_y = round((target_h - scaled_h) / 2 + (y / 100.0) * ((target_h - scaled_h) / 2))
        crop_top = 0
    else:
        crop_top = round((scaled_h - target_h) / 2 + (y / 100.0) * ((scaled_h - target_h) / 2))
        crop_top = max(0, min(scaled_h - target_h, crop_top))
        dest_y = 0

    visible_w = min(scaled_w, target_w)
    visible_h = min(scaled_h, target_h)
    visible = scaled.crop((crop_left, crop_top, crop_left + visible_w, crop_top + visible_h))
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    canvas.alpha_composite(visible, (max(0, dest_x), max(0, dest_y)))
    return canvas
