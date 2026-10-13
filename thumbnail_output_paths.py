"""Path helpers for DS Style artwork output.

Mirrored artwork follows the ROM's relative path below the selected SD root.
These helpers intentionally avoid platform-specific path interpretation for the
stored relative ROM path, which is serialized with POSIX separators.
"""
from pathlib import Path, PurePosixPath


def mirrored_thumbnail_path(
    output_root: Path,
    relative_rom_path: str,
    artwork_stem: str | None = None,
) -> Path:
    """Return an artwork path matching a ROM's relative directory.

    Example:
        relative_rom_path = "Game Boy/T/Tetris (World).gb"
        output_root = Path("IMGS")
        result = Path("IMGS/Game Boy/T/Tetris (World).bmp")

    ``artwork_stem`` defaults to the ROM filename stem. It is useful for callers
    that need to keep a custom display name separate from the mirrored filename.
    Absolute paths and parent traversal are rejected to prevent output escaping
    the selected artwork root.
    """
    relative = PurePosixPath(str(relative_rom_path).replace("\\", "/"))
    if (
        not relative.parts
        or relative.is_absolute()
        or any(part in ("", ".", "..") for part in relative.parts)
        or (relative.parts and ":" in relative.parts[0])
    ):
        raise ValueError(f"Unsafe relative ROM path: {relative_rom_path!r}")

    stem = artwork_stem if artwork_stem is not None else Path(relative.name).stem
    stem = str(stem).strip()
    if not stem or stem in (".", "..") or any(ch in stem for ch in '<>:"/\\|?*'):
        raise ValueError(f"Invalid artwork filename: {artwork_stem!r}")

    destination = Path(output_root).joinpath(*relative.parts[:-1], f"{stem}.bmp")
    # A second check guards against later changes to this helper and platform path
    # behavior; all user-controlled path components above are relative and safe.
    try:
        destination.relative_to(Path(output_root))
    except ValueError as exc:
        raise ValueError("Mirrored artwork path escaped the artwork root.") from exc
    return destination


def infer_relative_rom_path(rom_path: Path, system_name: str) -> str:
    """Infer a mirrored path when a manually selected ROM lives below its system folder.

    For example, selecting ``.../Game Boy/T/Tetris.gb`` will produce
    ``Game Boy/T/Tetris.gb``. If no directory exactly matches the detected system
    name, return an empty string and let the application use CUSTOM output.
    """
    path = Path(rom_path)
    expected = system_name.casefold().strip()
    if not expected:
        return ""
    parts = path.parts
    for index, part in enumerate(parts[:-1]):
        if part.casefold() == expected:
            return PurePosixPath(*parts[index:]).as_posix()
    return ""


def relative_path_from_root(root: Path, rom_path: Path, system_name: str = "") -> str:
    """Build the safe ROM-relative path recorded during an SD scan.

    If the user selects a console folder itself as the scan root, prepend that
    console folder so the result still mirrors a browser path such as
    ``/Game Boy/T/Tetris.gb``.
    """
    root_path = Path(root)
    path = Path(rom_path)
    try:
        relative = path.relative_to(root_path).as_posix()
    except ValueError:
        # Resolve once as a fallback for equivalent absolute paths.
        relative = path.resolve().relative_to(root_path.resolve()).as_posix()
    relative_parts = PurePosixPath(relative).parts
    if (
        system_name
        and root_path.name.casefold() == system_name.casefold()
        and (not relative_parts or relative_parts[0].casefold() != root_path.name.casefold())
    ):
        relative = PurePosixPath(root_path.name, relative).as_posix()
    return relative
