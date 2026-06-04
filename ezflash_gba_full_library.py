from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from ezflash_gba_thumbs import (
    LIBRETRO_RAW,
    app_dir,
    find_boxart_name,
    http_get,
    load_libretro_index,
    output_path_for_code,
    prepare_image,
    write_ezflash_bmp,
)


NOINTRO_GBA_DAT = (
    "https://raw.githubusercontent.com/libretro/libretro-database/master/"
    "metadat/no-intro/Nintendo%20-%20Game%20Boy%20Advance.dat"
)
DEFAULT_WIDTH = 80
DEFAULT_HEIGHT = 80


@dataclass(frozen=True)
class LibraryEntry:
    title: str
    code: str

    @property
    def path(self) -> Path:
        return Path(f"{self.title}.gba")


def decode_dat_string(value: str) -> str:
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def load_gba_library(cache_path: Path, refresh: bool = False) -> list[LibraryEntry]:
    if cache_path.exists() and not refresh:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return [LibraryEntry(title=item["title"], code=item["code"]) for item in data]

    dat_text = http_get(NOINTRO_GBA_DAT).decode("utf-8", errors="replace")
    entries: list[LibraryEntry] = []
    seen: set[tuple[str, str]] = set()

    for match in re.finditer(r"game\s*\((.*?)\n\)", dat_text, flags=re.S):
        block = match.group(1)
        name_match = re.search(r'^\s*name\s+"((?:\\"|[^"])*)"', block, flags=re.M)
        serial_match = re.search(r'^\s*serial\s+"([A-Z0-9]{4})"', block, flags=re.M)
        if not name_match or not serial_match:
            continue

        title = decode_dat_string(name_match.group(1))
        code = serial_match.group(1)
        key = (title, code)
        if key in seen:
            continue
        seen.add(key)
        entries.append(LibraryEntry(title=title, code=code))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps([entry.__dict__ for entry in entries], indent=2),
        encoding="utf-8",
    )
    return entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a full EZ Flash Omega DE GBA box-art thumbnail library."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output IMGS folder. If omitted, creates IMGS beside this tool.",
    )
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Thumbnail width")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Thumbnail height")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing BMPs")
    parser.add_argument("--refresh-index", action="store_true", help="Refresh cached online indexes")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only the first N entries. Useful for testing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_dir = app_dir()
    output_root = args.output or (base_dir / "IMGS")
    cache_dir = base_dir / "DS Style Thumbnail Scraper Cache"

    try:
        library = load_gba_library(cache_dir / "libretro_nointro_gba_library.json", args.refresh_index)
        boxart_index = load_libretro_index(cache_dir / "libretro_gba_boxarts.json", args.refresh_index)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Could not load online indexes: {exc}", file=sys.stderr)
        return 2

    if args.limit:
        library = library[: args.limit]

    made = 0
    skipped = 0
    missed = 0
    failed = 0

    print(f"Loaded {len(library)} GBA library entries.")
    for index, entry in enumerate(library, start=1):
        out_path = output_path_for_code(output_root, entry.code)
        if out_path.exists() and not args.overwrite:
            skipped += 1
            continue

        art_name = find_boxart_name(entry, boxart_index)
        if not art_name:
            print(f"miss: {entry.title} ({entry.code})")
            missed += 1
            continue

        try:
            url_name = urllib.parse.quote(art_name)
            image_data = http_get(LIBRETRO_RAW.format(name=url_name))
            image = prepare_image(image_data, args.width, args.height, "cover", (0.0, 0.5))
            write_ezflash_bmp(image, out_path)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"fail: {entry.title} ({entry.code}): {exc}")
            failed += 1
            continue

        made += 1
        if made % 25 == 0:
            print(f"made {made} thumbnails... ({index}/{len(library)})")

    print(
        "\nDone. "
        f"Created {made}; skipped existing {skipped}; missing art {missed}; failed {failed}."
    )
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    used_drop_in_mode = len(sys.argv) == 1
    exit_code = main()
    if used_drop_in_mode and getattr(sys, "frozen", False):
        try:
            input("\nPress Enter to close.")
        except EOFError:
            pass
    raise SystemExit(exit_code)
