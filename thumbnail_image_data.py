"""Helpers for validating image payloads received from external providers."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def is_valid_image_data(data: bytes | bytearray | memoryview | None) -> bool:
    """Return whether *data* contains a fully decodable raster image.

    Image endpoints can occasionally return an HTML error page, a Git LFS
    pointer, or a truncated response with HTTP 200. Pillow raises
    ``UnidentifiedImageError`` for many of these payloads. Validate the full
    image before caching so one bad response cannot abort an SD-card scan.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)) or not data:
        return False

    try:
        # load() forces decoding rather than checking only the header. A
        # successful Image.open() alone does not detect every truncated file.
        with Image.open(io.BytesIO(bytes(data))) as image:
            image.load()
        return True
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ):
        return False


def is_valid_image_file(path: str | Path, expected_size: tuple[int, int] | None = None) -> bool:
    """Return whether a local image file fully decodes and optionally has a size.

    Existing output images are only reused when their pixels are readable. When
    expected_size is supplied, malformed/stale thumbnails of the wrong dimensions
    are rebuilt instead of being mistaken for completed output.
    """
    try:
        with Image.open(Path(path)) as image:
            image.load()
            return expected_size is None or image.size == expected_size
    except (
        FileNotFoundError,
        PermissionError,
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
    ):
        return False
