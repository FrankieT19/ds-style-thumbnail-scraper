from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from ezflash_gba_full_library import load_gba_library
from ezflash_gba_thumbs import (
    app_dir,
    clean_title,
    normalize_for_match,
    output_path_for_code,
    prepare_image,
    title_match_score,
    write_ezflash_bmp,
)


DEFAULT_WIDTH = 80
DEFAULT_HEIGHT = 80
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass(frozen=True)
class ArtFile:
    path: Path
    title: str
    is_europe: bool


def iter_art_files(pack_root: Path) -> tuple[list[ArtFile], list[ArtFile]]:
    if pack_root.is_file():
        raise ValueError("Please unzip the art pack first, then choose the extracted folder.")

    primary_files: list[ArtFile] = []
    europe_files: list[ArtFile] = []
    for path in sorted(pack_root.rglob("*")):
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        relative_parts = {part.lower() for part in path.relative_to(pack_root).parts}
        art = ArtFile(path=path, title=clean_title(path.name), is_europe="europe" in relative_parts)
        if art.is_europe:
            europe_files.append(art)
        else:
            primary_files.append(art)
    return primary_files, europe_files


def build_art_index(art_files: list[ArtFile]) -> dict[str, list[ArtFile]]:
    index: dict[str, list[ArtFile]] = {}
    for art in art_files:
        index.setdefault(normalize_for_match(art.title), []).append(art)
    return index


def choose_preferred_art(candidates: list[ArtFile]) -> ArtFile:
    return sorted(
        candidates,
        key=lambda art: (
            "(Alt)" in art.path.name,
            "(USA)" not in art.path.name,
            art.path.name,
        ),
    )[0]


def find_best_art(title: str, art_index: dict[str, list[ArtFile]]) -> ArtFile | None:
    normalized_title = normalize_for_match(title)
    exact_candidates = art_index.get(normalized_title)
    if exact_candidates:
        return choose_preferred_art(exact_candidates)

    best_score = 0.0
    best_art: ArtFile | None = None

    for candidates in art_index.values():
        art = choose_preferred_art(candidates)
        score = title_match_score(title, art.title)
        if "(USA)" in art.path.name:
            score += 0.35
        if art.is_europe:
            score -= 0.1
        if "(Alt)" in art.path.name:
            score -= 0.15
        if score > best_score:
            best_score = score
            best_art = art

    return best_art if best_score >= 3.85 else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an unzipped GBA box-front art pack into EZ Flash thumbnail BMPs."
    )
    parser.add_argument(
        "pack",
        nargs="?",
        type=Path,
        default=None,
        help="Unzipped art pack folder. If omitted, uses the folder containing this tool.",
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
    parser.add_argument("--refresh-index", action="store_true", help="Refresh cached metadata")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_dir = app_dir()
    pack_root = args.pack or base_dir
    output_root = args.output or (base_dir / "IMGS")
    cache_path = base_dir / "DS Style Thumbnail Scraper Cache" / "libretro_nointro_gba_library.json"

    try:
        primary_art_files, europe_art_files = iter_art_files(pack_root)
        library = load_gba_library(cache_path, refresh=args.refresh_index)
    except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Could not prepare conversion: {exc}", file=sys.stderr)
        return 2

    if not primary_art_files and not europe_art_files:
        print("No image files found in the selected pack folder.", file=sys.stderr)
        return 1

    primary_art_index = build_art_index(primary_art_files)
    europe_art_index = build_art_index(europe_art_files)
    made = 0
    skipped = 0
    missed = 0
    failed = 0
    used_art_paths: set[Path] = set()

    print(f"Loaded {len(primary_art_files)} primary art file(s).")
    print(f"Loaded {len(europe_art_files)} Europe fallback art file(s).")
    print(f"Loaded {len(library)} GBA metadata entries.")

    for entry in library:
        out_path = output_path_for_code(output_root, entry.code)
        if out_path.exists() and not args.overwrite:
            skipped += 1
            continue

        art = find_best_art(entry.title, primary_art_index)
        if not art:
            art = find_best_art(entry.title, europe_art_index)
        if not art:
            missed += 1
            continue

        try:
            image_data = art.path.read_bytes()
            image = prepare_image(image_data, args.width, args.height, "cover", (0.5, 0.5))
            write_ezflash_bmp(image, out_path)
        except OSError as exc:
            print(f"fail: {entry.title} ({entry.code}) from {art.path.name}: {exc}")
            failed += 1
            continue

        used_art_paths.add(art.path)
        made += 1
        if made % 100 == 0:
            print(f"made {made} thumbnails...")

    print(
        "\nDone. "
        f"Created {made}; skipped existing {skipped}; missing matches {missed}; failed {failed}; "
        f"used {len(used_art_paths)} unique source image(s)."
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
