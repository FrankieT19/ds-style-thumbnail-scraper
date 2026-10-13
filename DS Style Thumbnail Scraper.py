from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import ctypes
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
import io
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from ezflash_gba_full_library import load_gba_library
from ezflash_gba_pack_converter import build_art_index, find_best_art, iter_art_files
from thumbnail_output_paths import infer_relative_rom_path, mirrored_thumbnail_path, relative_path_from_root
from thumbnail_image_data import is_valid_image_data, is_valid_image_file
from thumbnail_rendering import fit_image_to_canvas, should_fit_art
from rom_matching import compute_rom_hashes, strip_nointro_tags
from json_cache import write_json_atomic

from ezflash_gba_thumbs import (
    app_dir,
    clean_title,
    find_boxart_name,
    http_get,
    normalize_for_match,
    output_path_for_code,
    title_match_score,
    tokens_for_match,
    write_ezflash_bmp,
)


APP_NAME = "DS Style Thumbnail Scraper"
APP_VERSION = "1.10.5"
OUTPUT_FOLDER_NAME = "DS Style Thumbnail Scraper output"
CACHE_FOLDER_NAME = "DS Style Thumbnail Scraper Cache"
CONFIG_NAME = "thumbnail_scraper_settings.json"
DEFAULT_SEARCH = "Mario Kart - Super Circuit"
PREVIEW_RESULT_LIMIT = 64
REGION_ORDER = ["USA", "Europe", "Japan", "Other"]
SEARCH_IGNORED_TITLE_TOKENS = {
    "the",
    "of",
    "a",
    "an",
    "and",
    "version",
    "edition",
}
BUILD_PREVIEW_SAMPLES = {
    "USA": ["Mario Kart - Super Circuit"],
    "Europe": ["Mario Kart - Super Circuit"],
    "Japan": ["Mario Kart Advance", "Pokemon Pinball - Ruby & Sapphire"],
    "Other": ["Mario Golf - Advance Tour (Australia)", "Billy Hatcher Hyper Shoot (World)", "Chaoji Maliou 2"],
}
GBA_IGDB_PLATFORM_ID = 24
GBA_SCREENSCRAPER_SYSTEM_ID = 12
PROVIDER_VALUES = ["Libretro", "Local Pack"]
AUTOMATIC_PROVIDER_ORDER = ("Libretro", "TheGamesDB", "ScreenScraper", "IGDB")
DEFAULT_SYSTEM = "Game Boy Advance"
LIBRETRO_SYSTEMS = {
    "Game Boy Advance": {
        "repo": "Nintendo_-_Game_Boy_Advance",
        "extensions": (".gba", ".agb", ".bin", ".mb"),
    },
    "Game Boy": {"repo": "Nintendo_-_Game_Boy", "extensions": (".gb",)},
    "Game Boy Color": {"repo": "Nintendo_-_Game_Boy_Color", "extensions": (".gbc",)},
    "Nintendo Entertainment System": {
        "repo": "Nintendo_-_Nintendo_Entertainment_System",
        "extensions": (".nes",),
    },
    "Master System": {"repo": "Sega_-_Master_System_-_Mark_III", "extensions": (".sms",)},
    "Game Gear": {"repo": "Sega_-_Game_Gear", "extensions": (".gg",)},
    "SG-1000": {"repo": "Sega_-_SG-1000", "extensions": (".sg",)},
    "PC Engine": {"repo": "NEC_-_PC_Engine_-_TurboGrafx_16", "extensions": (".pce",)},
    "Neo Geo Pocket": {"repo": "SNK_-_Neo_Geo_Pocket", "extensions": (".ngp", ".ngc")},
    "Neo Geo Pocket Color": {"repo": "SNK_-_Neo_Geo_Pocket_Color", "extensions": (".ngpc",)},
    "WonderSwan": {"repo": "Bandai_-_WonderSwan", "extensions": (".ws",)},
    "WonderSwan Color": {"repo": "Bandai_-_WonderSwan_Color", "extensions": (".wsc",)},
    "MSX": {"repo": "Microsoft_-_MSX", "extensions": (".rom",)},
    "Watara Supervision": {"repo": "Watara_-_Supervision", "extensions": (".sv",)},
    "ZX Spectrum": {"repo": "Sinclair_-_ZX_Spectrum", "extensions": (".z80",)},
    "ColecoVision": {"repo": "Coleco_-_ColecoVision", "extensions": (".col",)},
    "Arcadia 2001": {"repo": "Emerson_-_Arcadia_2001", "extensions": (".arc",)},
    "Super Cassette Vision": {"repo": "Epoch_-_Super_Cassette_Vision", "extensions": (".sc",)},
}
SYSTEM_BY_EXTENSION = {
    extension: system
    for system, details in LIBRETRO_SYSTEMS.items()
    for extension in details["extensions"]
}
SCAN_EXCLUDED_FOLDERS = {
    "$recycle.bin",
    "system volume information",
    "system",
    "saver",
    "rts",
    "cheat",
    "patch",
    "imgs",
    "imgs2",
    "backup",
    "themes",
    "kernels",
}
LIBRETRO_SOURCE_FOLDERS = {
    "Box Art": "Named_Boxarts",
    "Gameplay Screenshot": "Named_Snaps",
    "Title Screen": "Named_Titles",
}
THEGAMESDB_BASE_URL = "https://api.thegamesdb.net"
THEGAMESDB_PLATFORM_ALIASES = {
    "Game Boy Advance": ("Nintendo Game Boy Advance", "Game Boy Advance"),
    "Game Boy": ("Nintendo Game Boy", "Game Boy"),
    "Game Boy Color": ("Nintendo Game Boy Color", "Game Boy Color"),
    "Nintendo Entertainment System": ("Nintendo Entertainment System (NES)", "Nintendo Entertainment System", "NES"),
    "Master System": ("Sega Master System", "Master System"),
    "Game Gear": ("Sega Game Gear", "Game Gear"),
    "SG-1000": ("SEGA SG-1000", "SG-1000"),
    "PC Engine": ("TurboGrafx 16", "TurboGrafx-16", "NEC PC Engine", "PC Engine"),
    "Neo Geo Pocket": ("Neo Geo Pocket",),
    "Neo Geo Pocket Color": ("Neo Geo Pocket Color",),
    "WonderSwan": ("WonderSwan",),
    "WonderSwan Color": ("WonderSwan Color",),
    "MSX": ("MSX",),
    "Watara Supervision": ("Watara Supervision",),
    "ZX Spectrum": ("Sinclair ZX Spectrum", "ZX Spectrum"),
    "ColecoVision": ("Colecovision", "ColecoVision"),
    "Arcadia 2001": ("Emerson Arcadia 2001", "Arcadia 2001"),
    "Super Cassette Vision": ("Epoch Super Cassette Vision", "Super Cassette Vision"),
}
SCREENSCRAPER_SYSTEM_ALIASES = {
    "Game Boy Advance": ("Game Boy Advance", "Nintendo Game Boy Advance", "GBA"),
    "Game Boy": ("Game Boy", "Nintendo Game Boy", "GB"),
    "Game Boy Color": ("Game Boy Color", "Nintendo Game Boy Color", "GBC"),
    "Nintendo Entertainment System": ("Nintendo Entertainment System", "Nintendo Entertainment System (NES)", "NES", "Famicom"),
    "Master System": ("Master System", "Sega Master System", "Mark III"),
    "Game Gear": ("Game Gear", "Sega Game Gear"),
    "SG-1000": ("SG-1000", "Sega SG-1000", "SEGA SG-1000"),
    "PC Engine": ("PC Engine", "NEC PC Engine", "TurboGrafx-16", "TurboGrafx 16"),
    "Neo Geo Pocket": ("Neo Geo Pocket", "SNK Neo Geo Pocket"),
    "Neo Geo Pocket Color": ("Neo Geo Pocket Color", "SNK Neo Geo Pocket Color"),
    "WonderSwan": ("WonderSwan", "Bandai WonderSwan"),
    "WonderSwan Color": ("WonderSwan Color", "Bandai WonderSwan Color"),
    "MSX": ("MSX", "MSX 1", "Microsoft MSX"),
    "Watara Supervision": ("Watara Supervision", "Supervision"),
    "ZX Spectrum": ("ZX Spectrum", "Sinclair ZX Spectrum"),
    "ColecoVision": ("ColecoVision", "Colecovision"),
    "Arcadia 2001": ("Arcadia 2001", "Emerson Arcadia 2001"),
    "Super Cassette Vision": ("Super Cassette Vision", "Epoch Super Cassette Vision"),
}
IGDB_PLATFORM_ALIASES = {
    "Game Boy Advance": ("Game Boy Advance", "Nintendo Game Boy Advance"),
    "Game Boy": ("Game Boy", "Nintendo Game Boy"),
    "Game Boy Color": ("Game Boy Color", "Nintendo Game Boy Color"),
    "Nintendo Entertainment System": ("Nintendo Entertainment System", "Nintendo Entertainment System (NES)", "Famicom"),
    "Master System": ("Master System", "Sega Master System"),
    "Game Gear": ("Game Gear", "Sega Game Gear"),
    "SG-1000": ("SG-1000", "Sega SG-1000"),
    "PC Engine": ("PC Engine", "TurboGrafx-16", "TurboGrafx-16/PC Engine"),
    "Neo Geo Pocket": ("Neo Geo Pocket",),
    "Neo Geo Pocket Color": ("Neo Geo Pocket Color",),
    "WonderSwan": ("WonderSwan",),
    "WonderSwan Color": ("WonderSwan Color",),
    "MSX": ("MSX", "MSX 1"),
    "Watara Supervision": ("Watara Supervision", "Supervision"),
    "ZX Spectrum": ("ZX Spectrum", "Sinclair ZX Spectrum"),
    "ColecoVision": ("ColecoVision", "Colecovision"),
    "Arcadia 2001": ("Arcadia 2001",),
    "Super Cassette Vision": ("Super Cassette Vision",),
}
# Extra folder names that local media collections (LaunchBox, ES-DE, Batocera,
# RetroPie, OnionOS, MiSTer, libretro-thumbnails and hand-sorted libraries) use to
# label a console. They are added to the system name, Libretro repo name and
# provider aliases above. Matching ignores case, spaces, hyphens and underscores,
# so "Game Boy", "GameBoy" and "game-boy" are one entry, and "TG16" also covers
# "TG-16". The text inside () or [] is kept when matching a full folder name.
LOCAL_PACK_DIRECTORY_ALIASES = {
    "Game Boy Advance": ("Nintendo GBA",),
    "Game Boy": (
        "Original Game Boy",
        "Nintendo Original Game Boy",
        "Game Boy Original",
        "Game Boy Classic",
        "Game Boy DMG",
        "Nintendo Game Boy DMG",
        "DMG",
    ),
    "Game Boy Color": (
        "Game Boy Colour",
        "Nintendo Game Boy Colour",
        "Game Boy Color GBC",
        "Game Boy Color CGB",
        "Nintendo GBC",
        "GB Color",
        "GB Colour",
        "CGB",
    ),
    "Nintendo Entertainment System": (
        "Original Nintendo",
        "Original Nintendo Entertainment System",
        "Nintendo NES",
        "Nintendo 8-bit",
        "8-bit Nintendo",
        "Family Computer",
        "Nintendo Family Computer",
        "Nintendo Famicom",
        "NES Famicom",
        "Famicom NES",
        "Nintendo NES Famicom",
        "FC",
    ),
    "Master System": (
        "Master System Mark III",
        "Master System Mark 3",
        "Sega Master System Mark 3",
        "Sega Mark III",
        "Sega Mark 3",
        "Mark 3",
        "SMS",
        "Sega SMS",
    ),
    "Game Gear": ("Sega GG", "GG", "Game Gear GG", "Sega Game Gear GG"),
    "PC Engine": (
        "PC Engine TurboGrafx-16",
        "TurboGrafx-16 PC Engine",
        "TurboGrafx-16 and PC Engine",
        "PC Engine and TurboGrafx-16",
        "NEC TurboGrafx-16",
        "NEC TurboGrafx",
        "TurboGrafx",
        "TG16",
        "TGFX16",
        "PCE",
        "NEC PCE",
    ),
    "Neo Geo Pocket": ("NGP", "SNK NGP", "Neo Geo Pocket NGP"),
    "Neo Geo Pocket Color": (
        "Neo Geo Pocket Colour",
        "SNK Neo Geo Pocket Colour",
        "Neo Geo Pocket Color NGPC",
        "SNK NGPC",
        "NGPC",
        "NGP Color",
        "NGP Colour",
    ),
}
# A bare brand name is only trusted when no console-specific folder appears
# anywhere in the same path. "Nintendo/Game Boy/..." therefore resolves to Game Boy
# and "GBA/Box Art/Nintendo/..." (a publisher folder) stays Game Boy Advance, while
# "Nintendo/Box Art/..." is treated as NES.
LOCAL_PACK_BROAD_DIRECTORY_ALIASES = {
    "Nintendo Entertainment System": ("Nintendo",),
}
# Consoles this scraper cannot scrape but whose folders commonly sit beside the
# supported ones and share game titles (Addams Family exists on NES, Game Boy, SNES,
# Genesis, Game Gear and more). Art inside these folders is never offered for a
# supported system when that system has no folder of its own.
LOCAL_PACK_OTHER_CONSOLE_FOLDERS = (
    "SNES", "Super NES", "Super Nintendo", "Super Nintendo Entertainment System",
    "Nintendo Super Nintendo Entertainment System", "Super Famicom",
    "Nintendo Super Famicom", "SFC",
    "Nintendo 64", "N64", "GameCube", "Nintendo GameCube", "Wii", "Nintendo Wii",
    "Nintendo DS", "NDS", "Nintendo DSi", "Nintendo 3DS", "3DS",
    "Virtual Boy", "Nintendo Virtual Boy", "Pokemon Mini",
    "Famicom Disk System", "Nintendo Famicom Disk System", "FDS",
    "Genesis", "Sega Genesis", "Mega Drive", "Sega Mega Drive", "Genesis Mega Drive",
    "Sega Genesis Mega Drive", "Mega Drive Genesis", "Sega Mega Drive Genesis",
    "Sega CD", "Mega CD", "Sega Mega CD", "Sega 32X", "32X", "Sega Saturn", "Saturn",
    "Sega Dreamcast", "Dreamcast",
    "PC Engine CD", "TurboGrafx CD", "TurboGrafx-16 CD", "SuperGrafx", "PC Engine SuperGrafx",
    "Neo Geo", "SNK Neo Geo", "Neo Geo AES", "Neo Geo MVS", "Neo Geo CD",
    "Atari 2600", "Atari 5200", "Atari 7800", "Atari Lynx", "Lynx", "Atari Jaguar", "Jaguar",
    "PlayStation", "Sony PlayStation", "PS1", "PSX", "PlayStation 2", "PS2", "PSP",
    "PlayStation Portable",
    "3DO", "Intellivision", "Mattel Intellivision", "Arcade", "MAME", "FBNeo",
)
# .ngc is listed under "Neo Geo Pocket" in LIBRETRO_SYSTEMS but is the usual
# Neo Geo Pocket Color extension, so either console's folder may serve both.
LOCAL_PACK_COMPATIBLE_SYSTEMS = {
    "Neo Geo Pocket": ("Neo Geo Pocket Color",),
    "Neo Geo Pocket Color": ("Neo Geo Pocket",),
}
LOCAL_PACK_OTHER_CONSOLE = "<other console>"


def _squash_folder_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold().replace("&", "and"))


def local_pack_folder_keys(folder_name: str) -> tuple[str, ...]:
    """Lookup keys for one folder name: the full name, then without () and [] text.

    The full name is tried first so "Game Boy (Color)" means Game Boy Color, while
    "NES (USA)" still falls back to "NES".
    """
    full = _squash_folder_name(folder_name)
    bare = _squash_folder_name(re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", folder_name))
    return tuple(dict.fromkeys(key for key in (full, bare) if key))


def _build_local_pack_folder_owners() -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    specific: dict[str, set[str]] = {}
    broad: dict[str, set[str]] = {}

    def add(table: dict[str, set[str]], name: str, owner: str) -> None:
        key = _squash_folder_name(name)
        if key:
            table.setdefault(key, set()).add(owner)

    for system, details in LIBRETRO_SYSTEMS.items():
        add(specific, system, system)
        add(specific, details.get("repo", ""), system)
        for mapping in (
            THEGAMESDB_PLATFORM_ALIASES,
            SCREENSCRAPER_SYSTEM_ALIASES,
            IGDB_PLATFORM_ALIASES,
            LOCAL_PACK_DIRECTORY_ALIASES,
        ):
            for alias in mapping.get(system, ()):
                add(specific, alias, system)
        for alias in LOCAL_PACK_BROAD_DIRECTORY_ALIASES.get(system, ()):
            add(broad, alias, system)
    for name in LOCAL_PACK_OTHER_CONSOLE_FOLDERS:
        add(specific, name, LOCAL_PACK_OTHER_CONSOLE)
    return (
        {key: frozenset(owners) for key, owners in specific.items()},
        {key: frozenset(owners) for key, owners in broad.items()},
    )


LOCAL_PACK_FOLDER_OWNERS, LOCAL_PACK_BROAD_FOLDER_OWNERS = _build_local_pack_folder_owners()


def local_pack_folder_owners(folder_name: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return (console-specific owners, broad-brand owners) for a folder name."""
    for key in local_pack_folder_keys(folder_name):
        owners = LOCAL_PACK_FOLDER_OWNERS.get(key)
        if owners:
            return owners, frozenset()
        owners = LOCAL_PACK_BROAD_FOLDER_OWNERS.get(key)
        if owners:
            return frozenset(), owners
    return frozenset(), frozenset()


GBA_SOURCE_CACHE_FILES = {
    "Named_Boxarts": "libretro_gba_boxarts.json",
    "Named_Snaps": "libretro_gba_snaps.json",
    "Named_Titles": "libretro_gba_titles.json",
}
GBA_TITLE_OFFSET = 0xA0
GBA_CODE_OFFSET = 0xAC
GBA_HEADER_CHECKSUM_OFFSET = 0xBD
GBA_HEADER_MIN_SIZE = 0xC0
WEB_HEADERS = {
    "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {APP_NAME}/{APP_VERSION}",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def libretro_repo(system: str) -> str:
    return LIBRETRO_SYSTEMS.get(system, LIBRETRO_SYSTEMS[DEFAULT_SYSTEM])["repo"]


def libretro_tree_url(system: str) -> str:
    return f"https://api.github.com/repos/libretro-thumbnails/{libretro_repo(system)}/git/trees/master?recursive=1"


def libretro_raw_url(system: str, folder: str, name: str) -> str:
    encoded_name = urllib.parse.quote(name)
    return (
        "https://raw.githubusercontent.com/libretro-thumbnails/"
        f"{libretro_repo(system)}/master/{folder}/{encoded_name}"
    )


def libretro_source_cache_path(base_dir: Path, folder: str, system: str = DEFAULT_SYSTEM) -> Path:
    if system == DEFAULT_SYSTEM and folder in GBA_SOURCE_CACHE_FILES:
        return base_dir / CACHE_FOLDER_NAME / GBA_SOURCE_CACHE_FILES[folder]
    repo = re.sub(r"[^a-z0-9]+", "_", libretro_repo(system).lower()).strip("_")
    source = re.sub(r"[^a-z0-9]+", "_", folder.lower()).strip("_")
    filename = f"libretro_{repo}_{source}.json"
    return base_dir / CACHE_FOLDER_NAME / filename


def request_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or WEB_HEADERS)
    try:
        return json.loads(urllib.request.urlopen(request, timeout=30).read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise LookupError("The provider refused the request (403 Forbidden). Check the account/API key, and try again later if the service is rate-limiting.") from exc
        raise


def post_json(url: str, body: str, headers: dict[str, str]) -> list | dict:
    request = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        return json.loads(urllib.request.urlopen(request, timeout=30).read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise LookupError("The provider refused the request (403 Forbidden). Check the account/API key, and try again later if the service is rate-limiting.") from exc
        raise


def post_form_json(url: str, fields: dict[str, str]) -> dict:
    """POST form-encoded fields and parse the JSON response (Twitch OAuth)."""
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": WEB_HEADERS.get("User-Agent", APP_NAME),
        },
        method="POST",
    )
    try:
        payload = json.loads(urllib.request.urlopen(request, timeout=30).read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise LookupError("The authentication service rejected the credentials. Check the Client ID and Client Secret.") from exc
        raise
    if not isinstance(payload, dict):
        raise LookupError("The authentication service returned an unexpected response.")
    return payload


def fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or WEB_HEADERS)
    try:
        return urllib.request.urlopen(request, timeout=30).read()
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise LookupError("The image host refused the download (403 Forbidden). Try another result/provider, or try again later.") from exc
        raise


def title_regions(title: str) -> set[str]:
    # Region names count only as complete words, avoiding titles such as
    # "Europeans" or "Japanese Garden" being treated as regional releases.
    value = str(title or "").casefold()
    regions: set[str] = set()
    if re.search(r"\b(?:usa|us)\b", value):
        regions.add("USA")
    if re.search(r"\b(?:europe|eu)\b", value):
        regions.add("Europe")
    if re.search(r"\b(?:japan|jp)\b", value):
        regions.add("Japan")
    other_markers = ("australia", "world", "china", "korea", "asia", "taiwan", "hong kong")
    if any(re.search(rf"\b{re.escape(marker)}\b", value) for marker in other_markers):
        regions.add("Other")
    return regions or {"Other"}


def content_tokens(value: str) -> set[str]:
    return {
        token
        for token in tokens_for_match(value)
        if token not in SEARCH_IGNORED_TITLE_TOKENS
        and len(token) > 1
    }


def title_search_compatible(query: str, candidate: str) -> bool:
    query_tokens = content_tokens(query)
    candidate_tokens = content_tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return False
    if query_tokens == candidate_tokens:
        return True

    normalized_query = normalize_for_match(query)
    normalized_candidate = normalize_for_match(candidate)
    if normalized_query == normalized_candidate:
        return True

    # Allows small naming differences like "Pokemon FireRed" vs
    # "Pokemon - FireRed Version" without letting sequels through.
    if normalized_query and normalized_candidate.startswith(normalized_query):
        suffix = normalized_candidate[len(normalized_query):]
        suffix_tokens = set(re.findall(r"[a-z0-9]+", suffix.lower()))
        return bool(suffix_tokens) and suffix_tokens <= SEARCH_IGNORED_TITLE_TOKENS

    return False


def variant_rank(title: str) -> int:
    """Return a penalty for non-standard releases; lower always wins.

    Provider APIs and filename indexes often return prototypes, demos, hacks,
    translations, and other non-retail variants alongside the retail game. Keep
    these candidates available for manual preview, but rank an unmarked retail
    release ahead of them when choosing a default result.
    """
    value = str(title or "").casefold().replace("_", " ")

    # A provider response explicitly marked as a ROM checksum match is an
    # exact-identity match, so it outranks even an otherwise unmarked retail
    # title. Hashing remains opt-in and is only queried after name matching fails.
    if re.search(r"\brom\s+(?:crc|md5|sha-?1|hash)\s+match\b", value):
        return -100

    rank = 0

    # Official rereleases/alternate revisions are less preferred than the
    # original retail title, but are ranked ahead of obvious non-retail builds.
    if re.search(r"\bvirtual[ -]?console\b", value):
        rank += 2
    if re.search(r"\b(?:alt|alternate|alternative)(?:\s*\d+)?\b", value):
        rank += 4
    if re.search(r"\brev(?:ision)?\s*\d+\b", value):
        rank += 2

    development_variant = re.search(
        r"\b(?:alpha|beta|proto(?:type)?|demo|sample|preview|unreleased|internal|"
        r"debug|wip|test(?:\s+(?:build|version|rom))?|development(?:\s+(?:build|version))?|"
        r"dev[ -]?build|pre[ -]?release|work[ -]?in[ -]?progress)\b",
        value,
    )
    modified_variant = re.search(
        r"\b(?:rom[ -]?hack|hack(?:ed|ing)?|mod(?:ded|ification)?|randomi[sz]er|"
        r"fan[ -]?translation|translation|translated|bootleg|pirate|trainer|patched|"
        r"redux|remix|homebrew|cheat(?:ed)?|repacked?)\b",
        value,
    )
    # Common GoodTools/ROM-set tags for hacks, bad dumps, and fan translations.
    dump_tag = re.search(r"\[(?:h\d*|b\d*|t\d?(?:[+-][a-z]{2,5})?)\]", value)
    if development_variant:
        rank += 5
    if modified_variant or dump_tag:
        rank += 6
    return rank


def provider_key(provider: str) -> str:
    if provider.startswith("IGDB"):
        return "IGDB"
    if provider.startswith("TheGamesDB"):
        return "TheGamesDB"
    if provider.startswith("ScreenScraper"):
        return "ScreenScraper"
    return provider


def load_libretro_source_index(
    cache_path: Path,
    folder: str,
    system: str = DEFAULT_SYSTEM,
    refresh: bool = False,
) -> list[str]:
    if cache_path.exists() and not refresh:
        try:
            cached_names = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached_names, list) and cached_names and all(
                isinstance(name, str) and name.lower().endswith(".png") for name in cached_names
            ):
                return cached_names
        except (OSError, ValueError, TypeError):
            pass
    data = json.loads(http_get(libretro_tree_url(system)).decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
        raise ValueError("Libretro returned an invalid thumbnail index")
    prefix = f"{folder}/"
    names = sorted(
        Path(item["path"]).name
        for item in data.get("tree", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and item["path"].startswith(prefix)
        and item["path"].lower().endswith(".png")
    )
    if not names:
        raise LookupError(f"Libretro returned no artwork entries for {system}/{folder}")
    write_json_atomic(cache_path, names)
    return names


def read_gba_header(path: Path) -> tuple[str, str]:
    data = path.read_bytes()[:GBA_HEADER_MIN_SIZE]
    if len(data) < GBA_HEADER_MIN_SIZE:
        raise ValueError("This file is too small to be a GBA ROM.")
    title = data[GBA_TITLE_OFFSET:GBA_CODE_OFFSET].decode("ascii", errors="replace").strip(" \0")
    code = data[GBA_CODE_OFFSET:GBA_CODE_OFFSET + 4].decode("ascii", errors="replace").strip(" \0")
    return title, code


def normalize_gba_code(value: str) -> str:
    code = "".join(ch for ch in value.upper() if ch.isalnum())
    if len(code) != 4:
        raise ValueError("The header code must be exactly 4 letters/numbers.")
    return code


def patched_gba_rom(original: bytes, new_code: str) -> bytes:
    if len(original) < GBA_HEADER_MIN_SIZE:
        raise ValueError("This file is too small to be a GBA ROM.")
    code = normalize_gba_code(new_code).encode("ascii")
    data = bytearray(original)
    data[GBA_CODE_OFFSET:GBA_CODE_OFFSET + 4] = code
    checksum = (-(sum(data[GBA_TITLE_OFFSET:GBA_HEADER_CHECKSUM_OFFSET]) + 0x19)) & 0xFF
    data[GBA_HEADER_CHECKSUM_OFFSET] = checksum
    return bytes(data)


@dataclass
class CropSettings:
    zoom: float = 1.0
    x: float = 0.0
    y: float = 0.0


@dataclass
class ProviderResult:
    provider: str
    label: str
    image_data: bytes
    system: str = DEFAULT_SYSTEM


@dataclass
class ExceptionRule:
    title: str
    code: str
    size: str
    provider: str
    label: str
    source: str = ""
    local_path: str = ""
    crop: dict | None = None


@dataclass
class CustomRomItem:
    rom_path: str
    title: str
    old_code: str
    new_code: str
    image_path: str = ""
    size: str = "80x80"
    crop: dict | None = None
    system: str = ""
    rom_relative_path: str = ""


@dataclass
class SdRomCandidate:
    path: Path
    system: str
    title: str
    relative: str
    libretro_art_name: str | None


@dataclass
class SdArtworkMatch:
    path: Path
    system: str
    art_name: str
    relative: str
    provider: str = "Libretro"
    image_data: bytes | None = None


class OperationProgressWindow:
    """Small responsive status window for long-running background operations."""

    def __init__(self, parent: tk.Misc, title: str, heading: str):
        self.parent = parent
        self.started_at = time.monotonic()
        self._progress_mode = "indeterminate"
        self._clock_after_id = None
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.configure(bg="#152235")
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)
        self.window.columnconfigure(0, weight=1)

        self.heading_var = tk.StringVar(value=heading)
        self.detail_var = tk.StringVar(value="The app is working. This window will update as work progresses.")
        self.elapsed_var = tk.StringVar(value="Elapsed: 00:00")
        self.progress_var = tk.DoubleVar(value=0.0)

        ttk.Label(
            self.window,
            text=title,
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 4))
        ttk.Label(
            self.window,
            textvariable=self.heading_var,
            style="Muted.TLabel",
            wraplength=520,
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(2, 8))
        self.progress_bar = ttk.Progressbar(
            self.window,
            orient="horizontal",
            mode="indeterminate",
            maximum=100,
            variable=self.progress_var,
            length=520,
        )
        self.progress_bar.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
        self.progress_bar.start(12)
        ttk.Label(
            self.window,
            textvariable=self.detail_var,
            style="Muted.TLabel",
            wraplength=520,
        ).grid(row=3, column=0, sticky="w", padx=18, pady=(0, 8))
        ttk.Label(
            self.window,
            textvariable=self.elapsed_var,
            style="Muted.TLabel",
        ).grid(row=4, column=0, sticky="w", padx=18, pady=(0, 16))

        self.window.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.window.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.window.winfo_height()) // 2)
        self.window.geometry(f"+{x}+{y}")
        self.window.grab_set()
        self._tick_elapsed()

    def _tick_elapsed(self):
        try:
            if not self.window.winfo_exists():
                return
            elapsed = max(0, int(time.monotonic() - self.started_at))
            minutes, seconds = divmod(elapsed, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                formatted = f"{minutes:02d}:{seconds:02d}"
            self.elapsed_var.set(f"Elapsed: {formatted}")
            self._clock_after_id = self.parent.after(1000, self._tick_elapsed)
        except tk.TclError:
            return

    def update_progress(
        self,
        heading: str,
        current: int | None = None,
        total: int | None = None,
        detail: str = "",
    ):
        try:
            if not self.window.winfo_exists():
                return
            self.heading_var.set(heading)
            self.detail_var.set(detail or "Please wait…")
            if current is not None and total is not None and total > 0:
                if self._progress_mode != "determinate":
                    self.progress_bar.stop()
                    self.progress_bar.configure(mode="determinate")
                    self._progress_mode = "determinate"
                self.progress_var.set(max(0.0, min(100.0, current / total * 100.0)))
            elif self._progress_mode != "indeterminate":
                self.progress_var.set(0.0)
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start(12)
                self._progress_mode = "indeterminate"
        except tk.TclError:
            pass

    def close(self):
        try:
            if self._clock_after_id is not None:
                self.parent.after_cancel(self._clock_after_id)
            self.progress_bar.stop()
            try:
                self.window.grab_release()
            except tk.TclError:
                pass
            self.window.destroy()
        except tk.TclError:
            pass


def validate_custom_art_name(value: str) -> str:
    name = value.strip()
    if name.lower().endswith(".bmp"):
        name = name[:-4].rstrip()
    if not name:
        raise ValueError("Enter the file or folder name, or select a file.")
    if any(ch in name for ch in '<>:"/\\|?*'):
        raise ValueError('Custom art names cannot contain: < > : " / \\ | ? *')
    if len(name) > 96:
        raise ValueError("Custom art names must be 96 characters or fewer.")
    return name


def output_path_for_custom_name(output_root: Path, name: str) -> Path:
    return output_root / "CUSTOM" / f"{validate_custom_art_name(name)}.bmp"


def display_libretro_name(name: str) -> str:
    return Path(name).stem.replace("_", " ")


def system_for_path(path: Path) -> str | None:
    return SYSTEM_BY_EXTENSION.get(path.suffix.casefold())


class Providers:
    def __init__(self, app: "ThumbnailScraperApp"):
        self.app = app
        self.libretro_indexes: dict[tuple[str, str], list[str]] = {}
        self.libretro_direct_indexes: dict[tuple, tuple[dict[str, str], list[str]]] = {}
        self.local_art_index = None
        self.local_art_index_root: Path | None = None
        self.local_art_files: list = []
        self.local_art_indexes_by_system: dict[str, dict[str, list]] = {}
        self.local_art_token_indexes_by_system: dict[str, dict[str, list]] = {}
        self._igdb_access_token = ""
        self._igdb_token_expires_at = 0.0
        self._igdb_platform_ids: dict[str, int] = {}
        self._igdb_platform_catalog: list[dict] | None = None
        self._screenscraper_system_records: list[dict] | None = None

    def search(
        self,
        provider: str,
        query: str,
        libretro_source: str | None = None,
        system: str = DEFAULT_SYSTEM,
    ) -> ProviderResult:
        results = self.search_many(
            provider,
            query,
            max_results=1,
            libretro_source=libretro_source,
            system=system,
        )
        if not results:
            raise LookupError("No artwork found.")
        return results[0]

    def search_many(
        self,
        provider: str,
        query: str,
        max_results: int | None = 20,
        libretro_source: str | None = None,
        system: str = DEFAULT_SYSTEM,
    ) -> list[ProviderResult]:
        provider = provider_key(provider)
        # Optional global preference: matching local art wins before provider lookups.
        if provider != "Local Pack" and self._local_pack_priority_enabled():
            try:
                local_results = self.search_local_pack_many(query, max_results, system=system)
                usable_local = [
                    result for result in local_results if is_valid_image_data(result.image_data)
                ]
                if usable_local:
                    return usable_local if max_results is None else usable_local[:max_results]
            except Exception:
                # A local miss must never block the ordinary provider flow.
                pass
        if provider == "Libretro":
            errors: list[str] = []
            try:
                libretro_results = self.search_libretro_many(query, max_results, libretro_source, system)
                usable_results = [
                    result for result in libretro_results if is_valid_image_data(result.image_data)
                ]
                if usable_results:
                    return usable_results
                raise LookupError("Libretro returned no usable image data for this match.")
            except Exception as libretro_error:
                errors.append(f"Libretro: {libretro_error}")
            return self.search_fallback_many(
                query,
                max_results=max_results,
                system=system,
                after_provider="Libretro",
                prior_errors=errors,
            )
        results = self._search_direct_many(provider, query, max_results, libretro_source, system)
        usable_results = [result for result in results if is_valid_image_data(result.image_data)]
        if not usable_results:
            raise LookupError(f"{provider} returned no valid or complete image data for {query!r}.")
        return usable_results if max_results is None else usable_results[:max_results]

    def _search_direct_many(
        self,
        provider: str,
        query: str,
        max_results: int | None,
        libretro_source: str | None,
        system: str,
    ) -> list[ProviderResult]:
        if provider == "Local Pack":
            return self.search_local_pack_many(query, max_results, system=system)
        if provider == "IGDB":
            return self.search_igdb_many(query, max_results, system=system)
        if provider == "TheGamesDB":
            return self.search_thegamesdb_many(query, max_results, system=system)
        if provider == "ScreenScraper":
            return self.search_screenscraper_many(query, max_results, system=system)
        if provider == "Libretro":
            return self.search_libretro_many(query, max_results, libretro_source, system)
        raise ValueError(f"Unknown provider: {provider}")

    def _credential_value(self, name: str) -> str:
        variable = getattr(self.app, name, None)
        return variable.get().strip() if variable is not None else ""

    def _local_pack_priority_enabled(self) -> bool:
        # Use the instance dictionary to avoid tkinter.Misc.__getattr__ recursion
        # for lightweight test doubles that do not create a Tcl interpreter.
        variable = vars(self.app).get("local_pack_priority_var")
        return bool(variable is not None and variable.get())

    def provider_is_configured(self, provider: str) -> bool:
        if provider == "TheGamesDB":
            return bool(self._credential_value("tgdb_key_var"))
        if provider == "ScreenScraper":
            return bool(
                self._credential_value("ss_dev_id_var")
                and self._credential_value("ss_dev_pass_var")
            )
        if provider == "IGDB":
            return bool(
                self._credential_value("igdb_client_var")
                and (self._credential_value("igdb_secret_var") or self._credential_value("igdb_token_var"))
            )
        return provider == "Libretro"

    def search_fallback_many(
        self,
        query: str,
        max_results: int | None = 1,
        system: str = DEFAULT_SYSTEM,
        after_provider: str = "Libretro",
        prior_errors: list[str] | None = None,
    ) -> list[ProviderResult]:
        """Search providers in the fixed automatic order after a miss/failure.

        Invalid image bytes count as a provider failure and do not block attempts
        against later services. Explicit manual provider searches still remain
        scoped to the provider the user selected.
        """
        order = list(AUTOMATIC_PROVIDER_ORDER)
        normalized_after = provider_key(after_provider)
        try:
            start_index = order.index(normalized_after) + 1
        except ValueError:
            start_index = 0
        errors = list(prior_errors or [])
        requested_limit = 20 if max_results is None else max(1, int(max_results))
        for provider in order[start_index:]:
            if not self.provider_is_configured(provider):
                if provider == "TheGamesDB":
                    detail = "API key not configured (Settings → Provider Credentials)"
                elif provider == "ScreenScraper":
                    detail = "developer ID/password not configured (Settings → Provider Credentials)"
                else:
                    detail = "Client ID and Client Secret not configured (Settings → Provider Credentials)"
                errors.append(f"{provider}: {detail}")
                continue
            try:
                results = self._search_direct_many(provider, query, requested_limit, None, system)
                usable = [result for result in results if is_valid_image_data(result.image_data)]
                if usable:
                    return usable[:requested_limit]
                raise LookupError("provider returned no usable or complete image data")
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
        details = "\n".join(f"• {detail}" for detail in errors)
        raise LookupError(
            f"No usable artwork found for {query!r} on {system}. The provider fallback chain was exhausted.\n\n{details}"
        )

    def get_libretro_index(self, system: str, folder: str) -> list[str]:
        key = (system, folder)
        if key not in self.libretro_indexes:
            cache = libretro_source_cache_path(self.app.base_dir, folder, system)
            self.libretro_indexes[key] = load_libretro_source_index(cache, folder, system)
        return self.libretro_indexes[key]

    def libretro_match_index(self, system: str, folder: str) -> tuple[dict[str, str], list[str]]:
        cache_key = (system, folder, tuple(self.app.ordered_regions()))
        if cache_key not in self.libretro_direct_indexes:
            use_region_filter = system == DEFAULT_SYSTEM
            allowed_index = sorted(
                [
                    name
                    for name in self.get_libretro_index(system, folder)
                    if not use_region_filter or self.app.region_allowed(name)
                ],
                key=lambda name: (
                    variant_rank(name),
                    self.app.region_priority(name) if use_region_filter else 0,
                    name.casefold(),
                ),
            )
            exact_index: dict[str, str] = {}
            for name in allowed_index:
                exact_index.setdefault(normalize_for_match(name), name)
            self.libretro_direct_indexes[cache_key] = (exact_index, allowed_index)
        return self.libretro_direct_indexes[cache_key]

    def find_libretro_art_name(self, query: str, system: str, folder: str) -> str | None:
        # SD scanning follows the files that are actually installed. Pack-region
        # preferences must not hide a World, Japan, or other regional ROM here.
        allowed_index = sorted(
            self.get_libretro_index(system, folder),
            key=lambda name: (variant_rank(name), name.casefold()),
        )
        literal_index = {Path(name).stem.casefold(): name for name in allowed_index}
        exact_index: dict[str, str] = {}
        for name in allowed_index:
            exact_index.setdefault(normalize_for_match(name), name)
        exact_literal = literal_index.get(Path(query).stem.casefold())
        # An exact beta/prototype/hack filename should not defeat an available
        # retail artwork file with the same normalized game title.
        if exact_literal and variant_rank(exact_literal) == 0:
            return exact_literal
        exact = exact_index.get(normalize_for_match(query)) or exact_literal
        if exact:
            return exact
        extension = LIBRETRO_SYSTEMS.get(system, LIBRETRO_SYSTEMS[DEFAULT_SYSTEM])["extensions"][0]
        candidate = type(
            "ScannedRom",
            (),
            {"path": Path(f"{query}{extension}"), "title": query, "code": "----"},
        )()
        return find_boxart_name(candidate, allowed_index)

    def search_libretro_many(
        self,
        query: str,
        max_results: int | None = 20,
        libretro_source: str | None = None,
        system: str = DEFAULT_SYSTEM,
    ) -> list[ProviderResult]:
        folder = LIBRETRO_SOURCE_FOLDERS.get(libretro_source or self.app.preview_libretro_source_var.get(), "Named_Boxarts")
        libretro_index = self.get_libretro_index(system, folder)
        search_queries = self.libretro_search_queries(query) if system == DEFAULT_SYSTEM else [query]
        scored = []
        for name in libretro_index:
            if system == DEFAULT_SYSTEM and not self.app.region_allowed(name):
                continue
            score = title_match_score(query, name)
            include = score >= 2.2 and title_search_compatible(query, name)
            normalized_name = normalize_for_match(name)
            for search_query in search_queries[1:]:
                alias_score = title_match_score(search_query, name)
                normalized_alias = normalize_for_match(search_query)
                alias_content = content_tokens(search_query)
                if not alias_content or not title_search_compatible(search_query, name):
                    continue
                strong_substring = (
                    len(normalized_alias) >= 8
                    and (normalized_alias in normalized_name or normalized_name in normalized_alias)
                )
                if alias_score >= 3.8 or strong_substring:
                    score = max(score, alias_score + 0.2)
                    include = True
            if include:
                scored.append((score, name))
        scored.sort(
            key=lambda item: (
                variant_rank(item[1]),
                -item[0],
                self.app.region_priority(item[1]) if system == DEFAULT_SYSTEM else 0,
                item[1].casefold(),
            )
        )
        if not scored:
            allowed_index = sorted(
                [
                    name
                    for name in libretro_index
                    if system != DEFAULT_SYSTEM or self.app.region_allowed(name)
                ],
                key=lambda name: (
                    self.app.region_priority(name) if system == DEFAULT_SYSTEM else 0,
                    name,
                ),
            )
            for search_query in search_queries:
                extension = LIBRETRO_SYSTEMS.get(system, LIBRETRO_SYSTEMS[DEFAULT_SYSTEM])["extensions"][0]
                fake = type("FakeRom", (), {"path": Path(f"{search_query}{extension}"), "title": search_query, "code": "----"})()
                art_name = find_boxart_name(fake, allowed_index)
                if art_name:
                    scored = [(99, art_name)]
                    break
        results = []
        limit = len(scored) if max_results is None else max_results
        art_names = [art_name for _score, art_name in scored[:limit] if art_name]
        if len(art_names) > 1:
            fetched: dict[str, bytes] = {}
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_name = {
                    executor.submit(
                        http_get,
                        libretro_raw_url(system, folder, art_name),
                    ): art_name
                    for art_name in art_names
                }
                for future in as_completed(future_to_name):
                    art_name = future_to_name[future]
                    try:
                        fetched[art_name] = future.result()
                    except Exception:
                        continue
            for art_name in art_names:
                if art_name in fetched:
                    results.append(ProviderResult("Libretro", art_name, fetched[art_name], system))
        else:
            for art_name in art_names:
                results.append(ProviderResult("Libretro", art_name, http_get(libretro_raw_url(system, folder, art_name)), system))
        if not results:
            raise LookupError(f"No Libretro artwork match found for {system}.")
        return results

    def direct_libretro_result(self, entry, libretro_source: str) -> ProviderResult:
        folder, art_name = self.direct_libretro_art_name(entry, libretro_source)
        return ProviderResult("Libretro", art_name, http_get(libretro_raw_url(DEFAULT_SYSTEM, folder, art_name)))

    def direct_libretro_art_map(self, libretro_source: str) -> dict[str, tuple[str, str]]:
        folder = LIBRETRO_SOURCE_FOLDERS.get(libretro_source, "Named_Boxarts")
        exact_index, _allowed_index = self.libretro_match_index(DEFAULT_SYSTEM, folder)
        art_by_code_root: dict[str, tuple[str, str]] = {}
        for entry in sorted(
            self.app.get_game_library(),
            key=lambda item: (variant_rank(item.title), self.app.region_priority(item.title), item.title.casefold()),
        ):
            if not entry.code or not self.app.region_allowed(entry.title):
                continue
            art_name = exact_index.get(normalize_for_match(entry.path.name))
            if not art_name:
                art_name = exact_index.get(normalize_for_match(entry.title))
            if art_name:
                art_by_code_root.setdefault(entry.code[:3], (folder, art_name))
        return art_by_code_root

    def direct_libretro_art_name(self, entry, libretro_source: str) -> tuple[str, str]:
        folder = LIBRETRO_SOURCE_FOLDERS.get(libretro_source, "Named_Boxarts")
        exact_index, allowed_index = self.libretro_match_index(DEFAULT_SYSTEM, folder)
        art_name = exact_index.get(normalize_for_match(entry.path.name))
        if not art_name:
            art_name = exact_index.get(normalize_for_match(entry.title))
        if not art_name and getattr(entry, "code", ""):
            code_root = entry.code[:3]
            aliases = [
                alias
                for alias in self.app.get_game_library()
                if alias.code and alias.code[:3] == code_root
            ]
            for alias in sorted(aliases, key=lambda item: (self.app.region_priority(item.title), item.title)):
                art_name = exact_index.get(normalize_for_match(alias.path.name))
                if not art_name:
                    art_name = exact_index.get(normalize_for_match(alias.title))
                if art_name:
                    break
            if not art_name:
                for alias in sorted(aliases, key=lambda item: (self.app.region_priority(item.title), item.title)):
                    art_name = find_boxart_name(alias, allowed_index)
                    if art_name:
                        break
        if not art_name:
            art_name = find_boxart_name(entry, allowed_index)
        if not art_name:
            raise LookupError("No Libretro box art match found.")
        return folder, art_name

    def libretro_search_queries(self, query: str) -> list[str]:
        queries = [query]
        normalized_query = normalize_for_match(query)
        if not normalized_query:
            return queries

        library = self.app.get_game_library()
        matched_code_roots = {
            entry.code[:3]
            for entry in library
            if entry.code
            and title_search_compatible(query, entry.title)
            and (
                title_match_score(query, entry.title) >= 2.2
                or normalized_query in normalize_for_match(entry.title)
                or normalize_for_match(entry.title) in normalized_query
            )
        }
        if matched_code_roots:
            for entry in sorted(
                library,
                key=lambda item: (variant_rank(item.title), self.app.region_priority(item.title), item.title.casefold()),
            ):
                if entry.code[:3] in matched_code_roots and self.app.region_allowed(entry.title):
                    queries.append(entry.title)

        return list(dict.fromkeys(queries))

    def local_pack_system_aliases(self, system: str) -> set[str]:
        """Normalized directory names used by common local artwork-pack layouts."""
        aliases = {_squash_folder_name(system)}
        aliases.update(key for key, owners in LOCAL_PACK_FOLDER_OWNERS.items() if system in owners)
        aliases.update(key for key, owners in LOCAL_PACK_BROAD_FOLDER_OWNERS.items() if system in owners)
        return {alias for alias in aliases if alias}

    def local_pack_art_files_for_system(self, art_files, pack_path: Path, system: str):
        """Scope matching to the folders that belong to this console.

        Each image is owned by the console named by its folders: the deepest
        console-specific folder wins ("Nintendo/Game Boy/..." is Game Boy), and a
        bare brand folder such as "Nintendo" is only used when the path has nothing
        more specific. Then:

        1. Images owned by the requested console are used if there are any.
        2. Otherwise images in folders that name no console are used, so a pack
           that mixes labeled and unlabeled folders still works. Art owned by a
           different console is never borrowed for this one.
        3. A pack with no recognizable console folders keeps the legacy
           whole-pack behavior.

        The configured pack is read-only: this only inspects paths.
        """
        accepted = {system, *LOCAL_PACK_COMPATIBLE_SYSTEMS.get(system, ())}
        folder_cache: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
        matched = []
        unlabeled = []
        recognized_console_folder = False
        for art in art_files:
            try:
                folder_parts = art.path.relative_to(pack_path).parts[:-1]
            except ValueError:
                continue
            owners = frozenset()
            broad_owners = frozenset()
            for part in reversed(folder_parts):
                if part not in folder_cache:
                    folder_cache[part] = local_pack_folder_owners(part)
                specific, broad = folder_cache[part]
                if specific:
                    owners = specific
                    break
                if broad and not broad_owners:
                    broad_owners = broad
            owners = owners or broad_owners
            if not owners:
                unlabeled.append(art)
                continue
            recognized_console_folder = True
            if owners & accepted:
                matched.append(art)
        if matched:
            return matched, True
        if recognized_console_folder:
            return unlabeled, True
        return list(art_files), False

    def search_local_pack_many(
        self, query: str, max_results: int | None = 20, system: str = DEFAULT_SYSTEM
    ) -> list[ProviderResult]:
        pack = self.app.local_pack_var.get().strip()
        if not pack:
            raise LookupError("Choose a local art pack folder first.")
        pack_path = Path(pack).expanduser()
        resolved_pack = pack_path.resolve()
        if self.local_art_index is None or self.local_art_index_root != resolved_pack:
            primary, europe = iter_art_files(pack_path)
            self.local_art_files = primary + europe
            self.local_art_index = build_art_index(self.local_art_files)
            self.local_art_index_root = resolved_pack
            self.local_art_indexes_by_system = {}
            self.local_art_token_indexes_by_system = {}

        # Console filtering and token indexes are built once per console, not per title.
        # This keeps local-first lookups usable for large media collections.
        index_key = system.casefold()
        if index_key not in self.local_art_indexes_by_system:
            scoped_art_files, has_console_folder = self.local_pack_art_files_for_system(
                self.local_art_files, pack_path, system
            )
            self.local_art_indexes_by_system[index_key] = (
                build_art_index(scoped_art_files) if has_console_folder else self.local_art_index
            )
        search_index = self.local_art_indexes_by_system[index_key]
        if index_key not in self.local_art_token_indexes_by_system:
            token_index: dict[str, list] = {}
            seen_paths: set[str] = set()
            for arts in search_index.values():
                for art in arts:
                    path_key = str(art.path).casefold()
                    if path_key in seen_paths:
                        continue
                    seen_paths.add(path_key)
                    for token in content_tokens(art.title):
                        token_index.setdefault(token, []).append(art)
            self.local_art_token_indexes_by_system[index_key] = token_index
        token_index = self.local_art_token_indexes_by_system[index_key]

        # Local pack filenames are normalized through clean_title(), which drops
        # release tags. Apply that cleanup only to the local comparison; online
        # searches retain No-Intro region tags as requested.
        match_query = clean_title(query).strip() or query.strip()
        query_tokens = content_tokens(match_query)
        exact_group = search_index.get(normalize_for_match(match_query), [])
        if exact_group:
            candidate_art_files = exact_group
        elif query_tokens:
            token_buckets = [token_index.get(token, []) for token in query_tokens]
            rarest_bucket = min(token_buckets, key=len, default=[])
            candidate_art_files = [
                art for art in rarest_bucket
                if query_tokens.issubset(content_tokens(art.title))
            ]
        else:
            candidate_art_files = [art for arts in search_index.values() for art in arts]

        candidates = []
        for art in candidate_art_files:
            if not self.app.region_allowed(self.local_art_region_text(art)):
                continue
            score = title_match_score(match_query, art.title)
            if score >= 2.2 and title_search_compatible(match_query, art.title):
                candidates.append((score, art))
        candidates.sort(
            key=lambda item: (
                # Parent directories describe pack organization, not the
                # release represented by this image.
                variant_rank(item[1].path.name),
                self.app.region_priority(self.local_art_region_text(item[1])),
                -item[0],
                item[1].path.name.casefold(),
            ),
        )
        if not candidates and (candidate_art_files or not query_tokens):
            fallback_index = build_art_index(candidate_art_files) if query_tokens else search_index
            art = find_best_art(match_query, fallback_index)
            candidates = [(99, art)] if art and self.app.region_allowed(self.local_art_region_text(art)) else []
        limit = len(candidates) if max_results is None else max_results
        results = [
            ProviderResult("Local Pack", self.local_art_label(art, pack_path), art.path.read_bytes(), system)
            for _score, art in candidates[:limit]
            if art
        ]
        if not results:
            raise LookupError(f"No local art match found for {query!r} on {system}.")
        return results

    def local_art_region_text(self, art) -> str:
        markers = [art.path.name]
        if art.is_europe:
            markers.append("Europe")
        return " ".join(markers)

    def local_art_label(self, art, pack_path: Path) -> str:
        try:
            return str(art.path.relative_to(pack_path))
        except ValueError:
            return art.path.name

    def _igdb_auth_headers(self, force_refresh: bool = False) -> dict[str, str]:
        """Return IGDB API headers, refreshing an OAuth app token as needed.

        New settings use Twitch Client ID + Client Secret. The prior manually
        supplied access-token setting remains as a compatibility fallback for
        existing settings files, although those tokens can expire.
        """
        client_id = self._credential_value("igdb_client_var")
        client_secret = self._credential_value("igdb_secret_var")
        legacy_token = self._credential_value("igdb_token_var")
        if not client_id:
            raise LookupError("IGDB needs a Twitch Client ID in Settings → Provider Credentials.")
        if client_secret:
            if not force_refresh and self._igdb_access_token and time.time() < self._igdb_token_expires_at:
                token = self._igdb_access_token
            else:
                response = post_form_json(
                    "https://id.twitch.tv/oauth2/token",
                    {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "grant_type": "client_credentials",
                    },
                )
                token = str(response.get("access_token") or "").strip()
                if not token:
                    raise LookupError("Twitch OAuth did not return an IGDB access token. Check the Client ID and Client Secret.")
                try:
                    lifetime = max(60, int(response.get("expires_in", 3600)))
                except (TypeError, ValueError):
                    lifetime = 3600
                self._igdb_access_token = token
                self._igdb_token_expires_at = time.time() + lifetime - min(120, lifetime // 10)
        elif legacy_token:
            token = legacy_token
        else:
            raise LookupError("IGDB needs both a Twitch Client ID and Client Secret in Settings → Provider Credentials.")
        return {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def test_igdb_credentials(self) -> int:
        headers = self._igdb_auth_headers(force_refresh=True)
        payload = post_json("https://api.igdb.com/v4/platforms", "fields id,name; limit 5;", headers)
        if not isinstance(payload, list) or not payload:
            raise LookupError("IGDB authenticated, but returned no platform data.")
        return len(payload)

    def _igdb_platform_id(self, system: str, headers: dict[str, str]) -> int:
        if system in self._igdb_platform_ids:
            return self._igdb_platform_ids[system]
        aliases = IGDB_PLATFORM_ALIASES.get(system, (system,))
        wanted = {self._platform_key(alias) for alias in aliases}
        if self._igdb_platform_catalog is None:
            payload = post_json(
                "https://api.igdb.com/v4/platforms",
                "fields id,name,slug; limit 500;",
                headers,
            )
            if not isinstance(payload, list):
                raise LookupError("IGDB returned an unexpected platform list.")
            self._igdb_platform_catalog = [item for item in payload if isinstance(item, dict)]
        for platform in self._igdb_platform_catalog:
            if self._platform_key(platform.get("name", "")) in wanted or self._platform_key(platform.get("slug", "")) in wanted:
                try:
                    platform_id = int(platform["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                self._igdb_platform_ids[system] = platform_id
                return platform_id
        raise LookupError(
            f"IGDB did not return a known platform ID for {system}; no cross-console search was performed."
        )

    def search_igdb_many(
        self,
        query: str,
        max_results: int | None = 20,
        system: str = DEFAULT_SYSTEM,
    ) -> list[ProviderResult]:
        headers = self._igdb_auth_headers()
        platform_id = self._igdb_platform_id(system, headers)
        safe_query = query.replace('\\', '\\\\').replace('"', '\\"')
        body = (
            "fields name,cover.image_id,artworks.image_id;"
            f' search "{safe_query}";'
            f" where platforms = ({platform_id}); limit 10;"
        )
        games = post_json("https://api.igdb.com/v4/games", body, headers)
        if not isinstance(games, list):
            raise LookupError("IGDB returned an unexpected game-search response.")
        games = sorted(
            (game for game in games if isinstance(game, dict)),
            key=lambda game: (
                variant_rank(str(game.get("name") or query)),
                -title_match_score(query, str(game.get("name") or query)),
                str(game.get("name") or query).casefold(),
            ),
        )
        results: list[ProviderResult] = []
        limit = 20 if max_results is None else max(1, int(max_results))
        for game in games:
            if not isinstance(game, dict):
                continue
            image_ids = []
            if isinstance(game.get("artworks"), list):
                image_ids.extend(
                    item.get("image_id") for item in game["artworks"]
                    if isinstance(item, dict) and item.get("image_id")
                )
            if isinstance(game.get("cover"), dict) and game["cover"].get("image_id"):
                image_ids.append(game["cover"]["image_id"])
            for image_id in image_ids[:5]:
                url = f"https://images.igdb.com/igdb/image/upload/t_720p/{image_id}.jpg"
                try:
                    image_data = fetch_bytes(url)
                    if not is_valid_image_data(image_data):
                        continue
                except Exception:
                    continue
                results.append(
                    ProviderResult("IGDB", f"{game.get('name', query)} - {image_id}", image_data, system)
                )
                if len(results) >= limit:
                    return results
        if not results:
            raise LookupError(f"No valid IGDB artwork found for {query!r} on {system}.")
        return results[:limit]

    @staticmethod
    def _platform_key(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(name).casefold())

    def thegamesdb_platforms(self) -> dict[str, int]:
        """Load TheGamesDB platform names/IDs, caching them for 30 days."""
        api_key = self.app.tgdb_key_var.get().strip()
        if not api_key:
            raise LookupError(
                "Automatic TheGamesDB fallback requires an API key. Add it under Settings → Provider Credentials."
            )
        cache_path = self.app.base_dir / CACHE_FOLDER_NAME / "thegamesdb_platforms.json"
        if cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                age = time.time() - float(cached.get("fetched_at", 0))
                raw = cached.get("platforms")
                if age < 30 * 24 * 60 * 60 and isinstance(raw, dict) and raw:
                    return {str(name): int(platform_id) for name, platform_id in raw.items()}
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass

        params = urllib.parse.urlencode({"apikey": api_key})
        response = request_json(f"{THEGAMESDB_BASE_URL}/v1/Platforms?{params}", WEB_HEADERS)
        platform_data = response.get("data", {}).get("platforms") or {}
        entries = []
        if isinstance(platform_data, dict):
            for key, value in platform_data.items():
                if not isinstance(value, dict):
                    continue
                platform_id = value.get("id", key)
                name = value.get("name") or value.get("platform_name")
                if name and str(platform_id).isdigit():
                    entries.append((str(name), int(platform_id)))
        elif isinstance(platform_data, list):
            for value in platform_data:
                if not isinstance(value, dict):
                    continue
                platform_id = value.get("id")
                name = value.get("name") or value.get("platform_name")
                if name and str(platform_id).isdigit():
                    entries.append((str(name), int(platform_id)))
        if not entries:
            raise LookupError("TheGamesDB returned no usable platform list.")

        platforms = {name: platform_id for name, platform_id in entries}
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"fetched_at": time.time(), "platforms": platforms}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        return platforms

    @staticmethod
    def test_thegamesdb_api_key(api_key: str) -> int:
        """Validate a TheGamesDB API key with a fresh authenticated request.

        This deliberately bypasses the platform cache so the Settings button
        verifies the key the user has currently entered, not stale cached data.
        """
        key = api_key.strip()
        if not key:
            raise LookupError("Enter your TheGamesDB API key first.")
        params = urllib.parse.urlencode({"apikey": key})
        response = request_json(f"{THEGAMESDB_BASE_URL}/v1/Platforms?{params}", WEB_HEADERS)
        payload = response.get("data", {}) if isinstance(response, dict) else {}
        platforms = payload.get("platforms") if isinstance(payload, dict) else None
        if isinstance(platforms, dict):
            count = sum(1 for value in platforms.values() if isinstance(value, dict))
        elif isinstance(platforms, list):
            count = sum(1 for value in platforms if isinstance(value, dict))
        else:
            count = 0
        if count <= 0:
            message = "TheGamesDB did not return a platform list. Check the API key and try again."
            if isinstance(response, dict):
                detail = response.get("status") or response.get("message")
                if detail:
                    message = f"TheGamesDB rejected or could not validate the key: {detail}"
            raise LookupError(message)
        return count

    def thegamesdb_platform_id(self, system: str) -> int:
        aliases = THEGAMESDB_PLATFORM_ALIASES.get(system, (system,))
        platforms = self.thegamesdb_platforms()
        by_normalized = {self._platform_key(name): platform_id for name, platform_id in platforms.items()}
        for alias in aliases:
            found = by_normalized.get(self._platform_key(alias))
            if found is not None:
                return found
        raise LookupError(
            f"TheGamesDB does not list a known platform mapping for {system}. "
            "No cross-console search was performed to avoid attaching artwork from the wrong system."
        )

    def search_thegamesdb_many(
        self,
        query: str,
        max_results: int | None = 20,
        system: str = DEFAULT_SYSTEM,
    ) -> list[ProviderResult]:
        api_key = self.app.tgdb_key_var.get().strip()
        if not api_key:
            raise LookupError("TheGamesDB fallback needs an API key. Add one under Settings → Provider Credentials.")
        platform_id = self.thegamesdb_platform_id(system)
        params = urllib.parse.urlencode(
            {
                "apikey": api_key,
                "name": query,
                "filter[platform]": str(platform_id),
                "include": "boxart,platform",
            }
        )
        data = request_json(f"{THEGAMESDB_BASE_URL}/v1.1/Games/ByGameName?{params}", WEB_HEADERS)
        payload = data.get("data", {})
        games = payload.get("games") or []
        games = sorted(
            (game for game in games if isinstance(game, dict)),
            key=lambda game: (
                variant_rank(str(game.get("game_title") or game.get("name") or query)),
                -title_match_score(query, str(game.get("game_title") or game.get("name") or query)),
                str(game.get("game_title") or game.get("name") or query).casefold(),
            ),
        )
        include = data.get("include", {})
        boxart = include.get("boxart", {})
        base = boxart.get("base_url", {}).get("original") or boxart.get("base_url", {}).get("large") or ""
        images = boxart.get("data") or boxart.get("images") or {}
        results: list[ProviderResult] = []
        limit = 20 if max_results is None else max_results

        def image_priority(image: dict) -> tuple[int, str]:
            side = str(image.get("side") or image.get("type") or "").casefold()
            filename = str(image.get("filename") or image.get("url") or "").casefold()
            is_front = side == "front" or "/front/" in filename or filename.startswith("front/")
            is_back = side == "back" or "/back/" in filename or filename.startswith("back/")
            return (0 if is_front else 2 if is_back else 1, filename)

        for game in games:
            game_title = str(game.get("game_title") or game.get("name") or query)
            # Do not accept a sequel/remake simply because the API's search is fuzzy.
            if title_match_score(query, game_title) < 1.6 or not title_search_compatible(query, game_title):
                continue
            game_id = str(game.get("id", ""))
            game_images = images.get(game_id) or images.get(str(game.get("id", ""))) or []
            if isinstance(game_images, dict):
                game_images = list(game_images.values())
            if not isinstance(game_images, list):
                continue
            for image in sorted((image for image in game_images if isinstance(image, dict)), key=image_priority):
                image_path = image.get("filename") or image.get("url") or image.get("thumb")
                if not image_path:
                    continue
                image_path = str(image_path).strip()
                if image_path.startswith(("http://", "https://")):
                    image_url = image_path
                elif image_path.startswith("/images/"):
                    image_url = urllib.parse.urljoin(base, image_path)
                else:
                    image_url = urllib.parse.urljoin(base, image_path.lstrip("/"))
                try:
                    image_data = fetch_bytes(image_url)
                    if not is_valid_image_data(image_data):
                        continue
                except Exception:
                    continue
                results.append(ProviderResult("TheGamesDB", f"{game_title} - {Path(str(image_path)).name}", image_data, system))
                if len(results) >= limit:
                    return results
        if not results:
            raise LookupError(f"No TheGamesDB box art match found for {query!r} on {system}.")
        return results

    def search_thegamesdb_hash_many(
        self,
        hashes: dict[str, str | int],
        query: str,
        max_results: int | None = 1,
        system: str = DEFAULT_SYSTEM,
    ) -> list[ProviderResult]:
        """Resolve a ROM hash through TheGamesDB, keeping results platform-scoped."""
        api_key = self._credential_value("tgdb_key_var")
        if not api_key:
            raise LookupError("TheGamesDB hash matching needs an API key in Settings → Provider Credentials.")
        platform_id = self.thegamesdb_platform_id(system)
        errors: list[str] = []
        # CRC is the lightest/commonest No-Intro key; MD5/SHA-1 are tried only if
        # the endpoint reports no usable artwork for the earlier checksum type.
        for hash_type in ("crc", "md5", "sha1"):
            hash_value = str(hashes.get(hash_type) or "").strip()
            if not hash_value:
                continue
            params = urllib.parse.urlencode(
                {
                    "apikey": api_key,
                    "hash": hash_value,
                    "filter[type]": hash_type,
                    "filter[platform]": str(platform_id),
                    "include": "boxart,platform",
                }
            )
            try:
                data = request_json(f"{THEGAMESDB_BASE_URL}/v1/Games/ByGameHash?{params}", WEB_HEADERS)
                payload = data.get("data", {}) if isinstance(data, dict) else {}
                games = payload.get("games") or [] if isinstance(payload, dict) else []
                if isinstance(games, dict):
                    games = list(games.values())
                if not isinstance(games, list) or not games:
                    errors.append(f"TheGamesDB {hash_type.upper()}: no game match")
                    continue
                include = data.get("include", {}) if isinstance(data, dict) else {}
                boxart = include.get("boxart", {}) if isinstance(include, dict) else {}
                base = boxart.get("base_url", {}).get("original") or boxart.get("base_url", {}).get("large") or ""
                images = boxart.get("data") or boxart.get("images") or {}
                results: list[ProviderResult] = []
                limit = 20 if max_results is None else max(1, int(max_results))

                def image_priority(image: dict) -> tuple[int, str]:
                    side = str(image.get("side") or image.get("type") or "").casefold()
                    filename = str(image.get("filename") or image.get("url") or "").casefold()
                    is_front = side == "front" or "/front/" in filename or filename.startswith("front/")
                    is_back = side == "back" or "/back/" in filename or filename.startswith("back/")
                    return (0 if is_front else 2 if is_back else 1, filename)

                for game in games:
                    if not isinstance(game, dict):
                        continue
                    game_title = str(game.get("game_title") or game.get("name") or query)
                    game_id = str(game.get("id", ""))
                    game_images = images.get(game_id) or images.get(str(game.get("id", ""))) or [] if isinstance(images, dict) else []
                    if isinstance(game_images, dict):
                        game_images = list(game_images.values())
                    if not isinstance(game_images, list):
                        continue
                    for image in sorted((item for item in game_images if isinstance(item, dict)), key=image_priority):
                        image_path = image.get("filename") or image.get("url") or image.get("thumb")
                        if not image_path:
                            continue
                        image_path = str(image_path).strip()
                        if image_path.startswith(("http://", "https://")):
                            image_url = image_path
                        elif image_path.startswith("/images/"):
                            image_url = urllib.parse.urljoin(base, image_path)
                        else:
                            image_url = urllib.parse.urljoin(base, image_path.lstrip("/"))
                        try:
                            image_data = fetch_bytes(image_url)
                            if not is_valid_image_data(image_data):
                                continue
                        except Exception:
                            continue
                        results.append(
                            ProviderResult(
                                "TheGamesDB",
                                f"{game_title} - {Path(str(image_path)).name} [ROM {hash_type.upper()} match]",
                                image_data,
                                system,
                            )
                        )
                        if len(results) >= limit:
                            return results
                if results:
                    return results
                errors.append(f"TheGamesDB {hash_type.upper()}: matching game had no usable box art")
            except Exception as exc:
                errors.append(f"TheGamesDB {hash_type.upper()}: {exc}")
        raise LookupError("; ".join(errors) if errors else "No usable TheGamesDB ROM-hash result.")

    def _screenscraper_credentials(self) -> dict[str, str]:
        devid = self._credential_value("ss_dev_id_var")
        devpassword = self._credential_value("ss_dev_pass_var")
        if not devid or not devpassword:
            raise LookupError(
                "ScreenScraper fallback needs a developer ID and developer password in Settings → Provider Credentials. "
                "ScreenScraper developer access may need to be requested from the service."
            )
        params = {
            "devid": devid,
            "devpassword": devpassword,
            "softname": APP_NAME,
            "output": "json",
        }
        ssid = self._credential_value("ss_user_var")
        sspassword = self._credential_value("ss_pass_var")
        if ssid and sspassword:
            params["ssid"] = ssid
            params["sspassword"] = sspassword
        elif ssid or sspassword:
            raise LookupError("ScreenScraper username and password must either both be filled in or both be blank.")
        return params

    @staticmethod
    def _screen_system_names(system_record: dict) -> list[str]:
        names: list[str] = []
        name_keys = {"nom", "name", "nomcourt", "nom_court", "nomlong", "nom_long", "nom_eu", "nom_us", "nom_jp", "nom_fr", "nom_en", "alias", "aliases"}

        def collect(value, key_hint: str = ""):
            if isinstance(value, str):
                if key_hint in name_keys or "nom" in key_hint or "name" in key_hint or "alias" in key_hint:
                    cleaned = value.strip()
                    if cleaned and cleaned not in names:
                        names.append(cleaned)
            elif isinstance(value, dict):
                for child_key, child_value in value.items():
                    normalized_key = str(child_key).casefold()
                    if normalized_key in name_keys or "nom" in normalized_key or "name" in normalized_key or "alias" in normalized_key:
                        collect(child_value, normalized_key)
            elif isinstance(value, list):
                for item in value:
                    collect(item, key_hint)

        for key, value in system_record.items():
            normalized_key = str(key).casefold()
            if normalized_key in name_keys or "nom" in normalized_key or "name" in normalized_key or "alias" in normalized_key:
                collect(value, normalized_key)
        return names

    def screenscraper_systems(self, refresh: bool = False) -> list[dict]:
        if self._screenscraper_system_records is not None and not refresh:
            return self._screenscraper_system_records
        params = self._screenscraper_credentials()
        payload = request_json(
            "https://www.screenscraper.fr/api2/systemesListe.php?" + urllib.parse.urlencode(params),
            WEB_HEADERS,
        )
        response = payload.get("response", {}) if isinstance(payload, dict) else {}
        systems_block = response.get("systemes", {}) if isinstance(response, dict) else {}
        systems = systems_block.get("systeme", []) if isinstance(systems_block, dict) else systems_block
        if isinstance(systems, dict):
            systems = [systems]
        if not isinstance(systems, list):
            systems = []
        records = []
        for item in systems:
            if not isinstance(item, dict):
                continue
            system_id = item.get("id") or item.get("systemeid")
            names = self._screen_system_names(item)
            if system_id is not None and names:
                records.append({"id": str(system_id), "names": names})
        if not records:
            detail = response.get("message") or response.get("erreur") or "no systems were returned"
            raise LookupError(f"ScreenScraper did not return a usable system list ({detail}). Check developer credentials.")
        self._screenscraper_system_records = records
        return records

    def screenscraper_system_id(self, system: str) -> str:
        aliases = SCREENSCRAPER_SYSTEM_ALIASES.get(system, (system,))
        wanted = {self._platform_key(alias) for alias in aliases}
        for record in self.screenscraper_systems():
            if wanted.intersection(self._platform_key(name) for name in record["names"]):
                return str(record["id"])
        raise LookupError(
            f"ScreenScraper has no known system mapping for {system}; no cross-console search was performed."
        )

    def test_screenscraper_credentials(self) -> int:
        systems = self.screenscraper_systems(refresh=True)
        return len(systems)

    def search_screenscraper_many(
        self,
        query: str,
        max_results: int | None = 20,
        system: str = DEFAULT_SYSTEM,
    ) -> list[ProviderResult]:
        params = self._screenscraper_credentials()
        params["systemeid"] = self.screenscraper_system_id(system)
        params["recherche"] = query
        data = request_json(
            "https://www.screenscraper.fr/api2/jeuRecherche.php?" + urllib.parse.urlencode(params),
            WEB_HEADERS,
        )
        response = data.get("response", {}) if isinstance(data, dict) else {}
        games_block = response.get("jeux", {}) if isinstance(response, dict) else {}
        games = games_block.get("jeu", []) if isinstance(games_block, dict) else games_block
        if isinstance(games, dict):
            games = [games]
        if not isinstance(games, list):
            games = []
        games = sorted(
            (game for game in games if isinstance(game, dict)),
            key=lambda game: (
                variant_rank(str(game.get("nom") or game.get("nom_eu") or game.get("name") or query)),
                -title_match_score(query, str(game.get("nom") or game.get("nom_eu") or game.get("name") or query)),
                str(game.get("nom") or game.get("nom_eu") or game.get("name") or query).casefold(),
            ),
        )
        results: list[ProviderResult] = []
        limit = 20 if max_results is None else max(1, int(max_results))
        preferred_types = ("box-2D", "box-3D", "wheel-hd", "wheel", "sstitle", "screenmarquee", "steamgrid")
        for game in games:
            if not isinstance(game, dict):
                continue
            title = game.get("nom") or game.get("nom_eu") or game.get("name") or query
            medias_block = game.get("medias", {})
            medias = medias_block.get("media", []) if isinstance(medias_block, dict) else medias_block
            if isinstance(medias, dict):
                medias = [medias]
            if not isinstance(medias, list):
                medias = []
            for preferred in preferred_types:
                for media in medias:
                    if not isinstance(media, dict) or media.get("type") != preferred or not media.get("url"):
                        continue
                    try:
                        image_data = fetch_bytes(str(media["url"]))
                        if not is_valid_image_data(image_data):
                            continue
                    except Exception:
                        continue
                    results.append(ProviderResult("ScreenScraper", f"{title} - {preferred}", image_data, system))
                    if len(results) >= limit:
                        return results
        if not results:
            detail = response.get("message") or response.get("erreur")
            suffix = f" ({detail})" if detail else ""
            raise LookupError(f"No valid ScreenScraper box art found for {query!r} on {system}{suffix}.")
        return results[:limit]

    def search_screenscraper_hash_many(
        self,
        rom_path: Path,
        hashes: dict[str, str | int],
        query: str,
        max_results: int | None = 1,
        system: str = DEFAULT_SYSTEM,
    ) -> list[ProviderResult]:
        """Identify a ROM via ScreenScraper's CRC/MD5/SHA-1 and size fields."""
        params = self._screenscraper_credentials()
        params.update(
            {
                "systemeid": self.screenscraper_system_id(system),
                "crc": str(hashes.get("crc", "")),
                "md5": str(hashes.get("md5", "")),
                "sha1": str(hashes.get("sha1", "")),
                "romtype": "rom",
                "romnom": rom_path.name,
                "romtaille": str(hashes.get("size", rom_path.stat().st_size)),
            }
        )
        data = request_json(
            "https://www.screenscraper.fr/api2/jeuInfos.php?" + urllib.parse.urlencode(params),
            WEB_HEADERS,
        )
        response = data.get("response", {}) if isinstance(data, dict) else {}
        game_value = response.get("jeu") or response.get("jeux") or response.get("game")
        if game_value is None and isinstance(response.get("medias"), (dict, list)):
            game_value = response
        if isinstance(game_value, dict):
            games = [game_value]
        elif isinstance(game_value, list):
            games = [item for item in game_value if isinstance(item, dict)]
        else:
            games = []
        results: list[ProviderResult] = []
        limit = 20 if max_results is None else max(1, int(max_results))
        preferred_types = ("box-2D", "box-3D", "wheel-hd", "wheel", "sstitle", "screenmarquee", "steamgrid")
        for game in games:
            title = game.get("nom") or game.get("nom_eu") or game.get("name") or query
            medias_block = game.get("medias", {})
            medias = medias_block.get("media", []) if isinstance(medias_block, dict) else medias_block
            if isinstance(medias, dict):
                medias = [medias]
            if not isinstance(medias, list):
                continue
            for preferred in preferred_types:
                for media in medias:
                    if not isinstance(media, dict) or media.get("type") != preferred or not media.get("url"):
                        continue
                    try:
                        image_data = fetch_bytes(str(media["url"]))
                        if not is_valid_image_data(image_data):
                            continue
                    except Exception:
                        continue
                    results.append(
                        ProviderResult(
                            "ScreenScraper", f"{title} - {preferred} [ROM hash match]", image_data, system
                        )
                    )
                    if len(results) >= limit:
                        return results
        if not results:
            detail = response.get("message") or response.get("erreur") if isinstance(response, dict) else None
            suffix = f" ({detail})" if detail else ""
            raise LookupError(
                f"No valid ScreenScraper artwork found by ROM hash for {rom_path.name} on {system}{suffix}."
            )
        return results[:limit]

    def search_hash_fallback(
        self, rom_path: Path, query: str, system: str = DEFAULT_SYSTEM
    ) -> list[ProviderResult]:
        """Run opt-in hash lookup after all local and name-based matching fails."""
        hashes = compute_rom_hashes(rom_path)
        errors: list[str] = []
        if self.provider_is_configured("TheGamesDB"):
            try:
                result = self.search_thegamesdb_hash_many(hashes, query, max_results=1, system=system)
                if result and is_valid_image_data(result[0].image_data):
                    return result[:1]
            except Exception as exc:
                errors.append(f"TheGamesDB hash lookup: {exc}")
        else:
            errors.append("TheGamesDB hash lookup skipped: API key not configured")

        if self.provider_is_configured("ScreenScraper"):
            try:
                result = self.search_screenscraper_hash_many(
                    rom_path, hashes, query, max_results=1, system=system
                )
                if result and is_valid_image_data(result[0].image_data):
                    return result[:1]
            except Exception as exc:
                errors.append(f"ScreenScraper hash lookup: {exc}")
        else:
            errors.append("ScreenScraper hash lookup skipped: developer credentials not configured")

        raise LookupError("No usable hash-based artwork match. " + "; ".join(errors))


def crop_image(image: Image.Image, size: tuple[int, int], crop: CropSettings) -> Image.Image:
    # Square box-art output should contain (not crop) distinctly portrait or
    # landscape source art. Title-art and near-square sources keep legacy crop.
    if should_fit_art(image, size):
        return fit_image_to_canvas(image, size, crop.zoom, crop.x, crop.y)

    image = image.convert("RGB")
    target_w, target_h = size
    min_scale = max(target_w / image.width, target_h / image.height)
    scale = max(min_scale, min_scale * crop.zoom)
    scaled_size = (max(target_w, round(image.width * scale)), max(target_h, round(image.height * scale)))
    image = image.resize(scaled_size, Image.Resampling.LANCZOS)
    max_x = image.width - target_w
    max_y = image.height - target_h
    x = round((max_x / 2) + (crop.x / 100) * (max_x / 2))
    y = round((max_y / 2) + (crop.y / 100) * (max_y / 2))
    x = max(0, min(max_x, x))
    y = max(0, min(max_y, y))
    return image.crop((x, y, x + target_w, y + target_h))


class ThumbnailScraperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        initial_width = min(1180, max(960, screen_width - 80))
        initial_height = min(830, max(620, screen_height - 80))
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(min(1040, initial_width), min(620, initial_height))
        self.base_dir = app_dir()
        self._seed_bundled_cache()
        self._set_window_icon()
        self.config_path = self.base_dir / CONFIG_NAME
        self.providers = Providers(self)
        self.current_result: ProviderResult | None = None
        self.result_options: list[ProviderResult] = []
        self.sd_scan_unmatched_games: list[dict[str, str]] = []
        self.active_sd_scan_game: dict[str, str] | None = None
        self.current_source_image: Image.Image | None = None
        self.build_result: ProviderResult | None = None
        self.build_source_image: Image.Image | None = None
        self.current_local_path = ""
        self.preview_photo = None
        self.build_preview_photo = None
        self.result_thumbs = []
        self._gallery_thumb_cache: dict[tuple, ImageTk.PhotoImage] = {}
        self.game_names: list[str] = []
        self.system_game_names: dict[str, list[str]] = {}
        self.game_library = []
        self.known_game_codes: set[str] = set()
        self.suggestion_box: tk.Listbox | None = None
        self.region_listboxes: list[tk.Listbox] = []
        self._settings_save_after_id = None
        self._build_preview_after_id = None
        self._build_preview_generation = 0
        self._build_preview_worker_running = False
        self._build_preview_pending = False
        self._preview_gallery_refresh_after_id = None
        self._suggestions_refresh_after_id = None
        self._saved_provider_credentials = None
        self.exceptions: list[ExceptionRule] = []
        self.custom_roms: list[CustomRomItem] = []
        self.custom_output_layout_var = tk.StringVar(value="Mirror ROM folders")
        self.custom_preview_photo = None
        self.running = False
        self.custom_build_running = False
        self.cancel_build_requested = False
        self.loading_custom_crop = False
        self.scan_running = False
        self.sd_scan_progress_window: OperationProgressWindow | None = None
        self.custom_art_progress_window: OperationProgressWindow | None = None
        self.tgdb_test_progress_window: OperationProgressWindow | None = None
        self.igdb_test_progress_window: OperationProgressWindow | None = None
        self.ss_test_progress_window: OperationProgressWindow | None = None
        self.tgdb_test_button: ttk.Button | None = None
        self.igdb_test_button: ttk.Button | None = None
        self.ss_test_button: ttk.Button | None = None
        self.tgdb_key_entry: ttk.Entry | None = None
        self.tgdb_key_reveal_button: ttk.Button | None = None
        self.tgdb_key_visible = False
        self.igdb_secret_entry: ttk.Entry | None = None
        self.igdb_secret_reveal_button: ttk.Button | None = None
        self.igdb_secret_visible = False
        self.ss_dev_pass_entry: ttk.Entry | None = None
        self.ss_dev_pass_reveal_button: ttk.Button | None = None
        self.ss_dev_pass_visible = False
        self.ss_pass_entry: ttk.Entry | None = None
        self.ss_pass_reveal_button: ttk.Button | None = None
        self.ss_pass_visible = False

        self.build_provider_var = tk.StringVar(value="Libretro")
        self.preview_provider_var = tk.StringVar(value="Libretro")
        self.build_libretro_source_var = tk.StringVar(value="Box Art")
        self.preview_libretro_source_var = tk.StringVar(value="Box Art")
        self.preview_system_var = tk.StringVar(value=DEFAULT_SYSTEM)
        self.size_var = tk.StringVar(value="80x80")
        self.search_var = tk.StringVar(value=DEFAULT_SEARCH)
        self.result_choice_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.build_status_var = tk.StringVar(value="Ready to build.")
        self.build_output_var = tk.StringVar(value="")
        self.build_progress_var = tk.DoubleVar(value=0.0)
        self.local_pack_var = tk.StringVar()
        self.local_pack_priority_var = tk.BooleanVar(value=False)
        self.igdb_client_var = tk.StringVar()
        self.igdb_secret_var = tk.StringVar()
        # Preserved only to support settings files made before automatic OAuth
        # support. New installs should supply the Client Secret, not an access token.
        self.igdb_token_var = tk.StringVar()
        self.tgdb_key_var = tk.StringVar()
        self.ss_dev_id_var = tk.StringVar()
        self.ss_dev_pass_var = tk.StringVar()
        self.ss_user_var = tk.StringVar()
        self.ss_pass_var = tk.StringVar()
        self.region_order = REGION_ORDER.copy()
        self.region_enabled = {region: True for region in REGION_ORDER}
        self.rom_region_vars = {region: tk.BooleanVar(value=True) for region in REGION_ORDER}
        self.exceptions_only_var = tk.BooleanVar(value=False)
        self.zoom_var = tk.DoubleVar(value=1.0)
        self.crop_x_var = tk.DoubleVar(value=0.0)
        self.crop_y_var = tk.DoubleVar(value=0.0)
        self.build_zoom_var = tk.DoubleVar(value=1.0)
        self.build_crop_x_var = tk.DoubleVar(value=0.0)
        self.build_crop_y_var = tk.DoubleVar(value=0.0)
        self.custom_zoom_var = tk.DoubleVar(value=1.0)
        self.custom_crop_x_var = tk.DoubleVar(value=0.0)
        self.custom_crop_y_var = tk.DoubleVar(value=0.0)

        self._style()
        self._build_ui()
        self.after(50, self._enable_dark_title_bar)
        self._load_settings()
        self._load_game_names_async()
        self.after(250, self.build_preview_search)

    def _seed_bundled_cache(self):
        cache_dir = self.base_dir / CACHE_FOLDER_NAME
        legacy_cache = self.base_dir / ".cache"
        if legacy_cache.exists():
            cache_dir.mkdir(exist_ok=True)
            for source in legacy_cache.iterdir():
                target = cache_dir / source.name
                if source.is_file() and not target.exists():
                    try:
                        shutil.move(str(source), str(target))
                    except OSError:
                        pass
            try:
                legacy_cache.rmdir()
            except OSError:
                pass

        bundled_cache = Path(getattr(sys, "_MEIPASS", self.base_dir)) / CACHE_FOLDER_NAME
        if not bundled_cache.exists():
            return
        cache_dir.mkdir(exist_ok=True)
        for filename in (
            "libretro_nointro_gba_library.json",
            "libretro_gba_boxarts.json",
            "libretro_gba_snaps.json",
            "libretro_gba_titles.json",
        ):
            source = bundled_cache / filename
            target = cache_dir / filename
            if source.exists() and not target.exists():
                try:
                    shutil.copyfile(source, target)
                except OSError:
                    pass

    def _style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        base = "#0d1624"
        surface = "#152235"
        control = "#20314a"
        edge = surface
        self.configure(bg=base)
        self.option_add("*TCombobox*Listbox.background", "#101a29")
        self.option_add("*TCombobox*Listbox.foreground", "#edf4fb")
        self.option_add("*TCombobox*Listbox.selectBackground", "#263e5d")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        style.configure("TFrame", background=base)
        style.configure("Panel.TFrame", background=surface, relief="flat", borderwidth=0)
        style.configure("Title.TLabel", background=base, foreground="#ffffff", font=("Segoe UI", 20, "bold"))
        style.configure("Sub.TLabel", background=base, foreground="#b8c7d8", font=("Segoe UI", 10))
        style.configure("HeaderVersion.TLabel", background=base, foreground="#2c405f", font=("Segoe UI", 10))
        style.configure("TLabel", background=surface, foreground="#f4f8fc", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=surface, foreground="#ffffff", font=("Segoe UI", 12, "bold"))
        style.configure("Muted.TLabel", background=surface, foreground="#aebfd2", font=("Segoe UI", 10))
        style.configure("TButton", background=control, foreground="#f4f8fc", borderwidth=0, focusthickness=0, focuscolor=control, relief="flat", font=("Segoe UI", 10), padding=(10, 6))
        style.map("TButton", background=[("active", "#263a57"), ("pressed", "#1c2b41"), ("focus", control)], foreground=[("disabled", "#718196")], relief=[("pressed", "flat"), ("!pressed", "flat")])
        style.configure("Accent.TButton", background="#2a5caa", foreground="#ffffff", borderwidth=0, focusthickness=0, focuscolor="#2a5caa", relief="flat", font=("Segoe UI", 10, "bold"), padding=(12, 7))
        style.map("Accent.TButton", background=[("active", "#3269bf"), ("pressed", "#244f94"), ("focus", "#2a5caa")], relief=[("pressed", "flat"), ("!pressed", "flat")])
        style.configure("TNotebook", background=base, borderwidth=0, tabmargins=(0, 0, 18, 0))
        style.configure("TNotebook", bordercolor=edge, lightcolor=edge, darkcolor=edge)
        style.configure("TNotebook.Tab", background=base, foreground="#8fa1b5", borderwidth=1, focusthickness=0, focuscolor=surface, font=("Segoe UI", 10), padding=(14, 8))
        style.configure("TNotebook.Tab", bordercolor=edge, lightcolor=edge, darkcolor=edge)
        style.map("TNotebook.Tab", background=[("selected", surface), ("active", "#101c2d"), ("pressed", "#101c2d"), ("focus", base)], foreground=[("selected", "#ffffff"), ("active", "#c4d0dc")], bordercolor=[("selected", surface), ("active", surface), ("!selected", surface)], lightcolor=[("selected", surface), ("active", surface), ("!selected", surface)], darkcolor=[("selected", surface), ("active", surface), ("!selected", surface)], padding=[("selected", (14, 8)), ("active", (14, 8)), ("pressed", (14, 8))])
        style.configure("TCombobox", fieldbackground="#101a29", background=control, foreground="#edf4fb", arrowcolor="#dce7f3", selectbackground="#101a29", selectforeground="#edf4fb", bordercolor=edge, lightcolor=edge, darkcolor=edge, insertcolor="#ffffff", borderwidth=0, font=("Segoe UI", 10))
        style.map("TCombobox", fieldbackground=[("readonly", "#101a29"), ("!disabled", "#101a29"), ("focus", "#101a29")], foreground=[("readonly", "#edf4fb"), ("!disabled", "#edf4fb"), ("focus", "#ffffff")], selectbackground=[("readonly", "#101a29"), ("focus", "#263e5d")], selectforeground=[("readonly", "#edf4fb"), ("focus", "#ffffff")], background=[("active", "#263a57"), ("pressed", "#1c2b41")], bordercolor=[("focus", edge), ("!focus", edge)])
        style.configure("TEntry", fieldbackground="#101a29", foreground="#edf4fb", insertcolor="#ffffff", borderwidth=0, bordercolor=edge, lightcolor=edge, darkcolor=edge)
        style.configure("TCheckbutton", background=surface, foreground="#f4f8fc", font=("Segoe UI", 10), focuscolor=surface)
        style.map("TCheckbutton", background=[("active", surface), ("focus", surface)], foreground=[("active", "#ffffff")])
        style.configure("Treeview", background="#101a29", foreground="#edf4fb", fieldbackground="#101a29", borderwidth=0, font=("Segoe UI", 10), rowheight=28)
        style.map("Treeview", background=[("selected", "#263e5d")], foreground=[("selected", "#ffffff")])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Treeview.Heading", background=control, foreground="#ffffff", borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("Treeview.Heading", background=[("active", control), ("pressed", control), ("!active", control)], foreground=[("active", "#ffffff")])
        style.configure("Vertical.TScrollbar", background="#20314a", troughcolor="#101a29", bordercolor="#152235", arrowcolor="#dce7f3", lightcolor="#20314a", darkcolor="#20314a", relief="flat", borderwidth=0)
        style.configure("Horizontal.TScrollbar", background="#20314a", troughcolor="#101a29", bordercolor="#152235", arrowcolor="#dce7f3", lightcolor="#20314a", darkcolor="#20314a", relief="flat", borderwidth=0)
        style.map("Vertical.TScrollbar", background=[("active", "#263a57"), ("pressed", "#1c2b41")])
        style.map("Horizontal.TScrollbar", background=[("active", "#263a57"), ("pressed", "#1c2b41")])
        style.configure("Horizontal.TProgressbar", background="#2a5caa", troughcolor="#101a29", bordercolor="#152235", lightcolor="#2a5caa", darkcolor="#2a5caa")


    def _sync_tree_columns(self, tree: ttk.Treeview, widths: dict[str, float]):
        def sync(_event=None):
            total = max(1, tree.winfo_width())
            for column, ratio in widths.items():
                tree.column(column, width=max(48, round(total * ratio)))
        tree.bind("<Configure>", sync)
        self.after(50, sync)

    def _sync_tree_scrollbar(self, tree: ttk.Treeview, scrollbar: ttk.Scrollbar):
        def sync(_event=None):
            row_count = len(tree.get_children())
            visible = int(tree.cget("height"))
            if row_count > visible:
                scrollbar.grid()
            else:
                scrollbar.grid_remove()
        tree.bind("<<TreeviewOpen>>", sync, add="+")
        self.after(50, sync)
        return sync

    def _set_gallery_scrollbar(self, first: str, last: str):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.gallery_ybar.grid_remove()
        else:
            self.gallery_ybar.grid()
        self.gallery_ybar.set(first, last)

    def _sync_gallery_scroll_area(self, _event=None):
        self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))

    def _sync_gallery_canvas_width(self, event):
        self.gallery_canvas.itemconfigure(self.gallery_window, width=max(1, event.width))
        self._sync_gallery_scroll_area()

    def _scroll_gallery(self, event):
        if self.gallery_ybar.winfo_ismapped():
            self.gallery_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        return None

    def _enable_gallery_mousewheel(self, _event=None):
        self.gallery_canvas.bind_all("<MouseWheel>", self._scroll_gallery)

    def _disable_gallery_mousewheel(self, _event=None):
        self.gallery_canvas.unbind_all("<MouseWheel>")

    def _build_region_order_control(self, parent, scope: str = "build"):
        """Build one region-priority control with a tab-specific update policy."""
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(anchor="w")
        region_list = tk.Listbox(
            frame,
            height=4,
            width=16,
            exportselection=False,
            bg="#101a29",
            fg="#edf4fb",
            selectbackground="#263e5d",
            selectforeground="#ffffff",
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 9),
        )
        region_list.grid(row=0, column=0, rowspan=3, sticky="nsw")
        ttk.Button(frame, text="Move Up", command=lambda lb=region_list, tab_scope=scope: self.move_region(lb, -1, tab_scope)).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        ttk.Button(frame, text="Move Down", command=lambda lb=region_list, tab_scope=scope: self.move_region(lb, 1, tab_scope)).grid(row=1, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(frame, text="Toggle Region", command=lambda lb=region_list, tab_scope=scope: self.toggle_region(lb, tab_scope)).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))
        region_list.bind("<space>", lambda _event, lb=region_list, tab_scope=scope: self.toggle_region(lb, tab_scope))
        region_list.bind("<Double-Button-1>", lambda _event, lb=region_list, tab_scope=scope: self.toggle_region(lb, tab_scope))
        self.region_listboxes.append(region_list)
        self.refresh_region_lists()
        return frame

    def _build_rom_region_control(self, parent):
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(anchor="w", fill="x")
        for index, region in enumerate(REGION_ORDER):
            ttk.Checkbutton(
                frame,
                text=region,
                variable=self.rom_region_vars[region],
                command=self.on_rom_region_change,
            ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0 if index % 2 == 0 else 18, 0), pady=(0, 3))
        return frame

    def _build_ui(self):
        header = ttk.Frame(self, style="TFrame", padding=(18, 16, 18, 8))
        header.pack(fill="x")
        bundled_dir = Path(getattr(sys, "_MEIPASS", self.base_dir))
        logo_paths = [
            self.base_dir / "LogoBig.png",
            bundled_dir / "LogoBig.png",
        ]
        logo_path = next((path for path in logo_paths if path.exists()), None)
        if logo_path:
            try:
                img = Image.open(logo_path).resize((210, 78), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(img)
                tk.Label(header, image=self.logo_photo, bg="#0d1624").pack(side="left", padx=(0, 16))
            except OSError:
                pass
        title_box = ttk.Frame(header, style="TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Find, preview, and build DS Style artwork.", style="Sub.TLabel").pack(anchor="w", pady=(3, 0))
        version_box = ttk.Frame(header, style="TFrame")
        version_box.pack(side="right", anchor="n")
        ttk.Label(version_box, text=f"DS Style Thumbnail Scraper v{APP_VERSION}", style="HeaderVersion.TLabel").pack(anchor="e")
        ttk.Label(version_box, text="For DS Style v7.4", style="HeaderVersion.TLabel").pack(anchor="e", pady=(4, 0))

        notebook = ttk.Notebook(self)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.build_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        self.preview_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        self.custom_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        self.exceptions_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        self.settings_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        notebook.add(self.build_tab, text="Build Pack")
        notebook.add(self.preview_tab, text="Search & Preview")
        notebook.add(self.custom_tab, text="Custom Art")
        notebook.add(self.exceptions_tab, text="Exceptions")
        notebook.add(self.settings_tab, text="Settings")
        notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self._build_build_tab()
        self._build_preview_tab()
        self._build_custom_tab()
        self._build_exceptions_tab()
        self._build_settings_tab()

        footer = ttk.Frame(self, style="TFrame", padding=(18, 0, 18, 10))
        footer.pack(fill="x")
        self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Sub.TLabel", wraplength=900)
        self.status_label.pack(side="left", fill="x", expand=True)
        footer.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(260, event.width - 36)))

    def _set_window_icon(self):
        bundled_dir = Path(getattr(sys, "_MEIPASS", self.base_dir))
        icon_paths = [
            self.base_dir / "LogoSquareThumbnailScraper.ico",
            bundled_dir / "LogoSquareThumbnailScraper.ico",
        ]
        icon_path = next((path for path in icon_paths if path.exists()), None)
        if icon_path:
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

    def _enable_dark_title_bar(self):
        if sys.platform != "win32":
            return
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            value = ctypes.c_int(1)
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if result == 0:
                    break
            self.update()
        except Exception:
            pass

    def _build_build_tab(self):
        left = ttk.Frame(self.build_tab, style="Panel.TFrame")
        left.pack(side="left", fill="y", padx=(0, 18))
        source_options = ttk.Frame(left, style="Panel.TFrame")
        source_options.pack(side="left", fill="y", padx=(0, 18))
        region_options = ttk.Frame(left, style="Panel.TFrame")
        region_options.pack(side="left", fill="y")

        ttk.Label(source_options, text="Pack Options", style="Section.TLabel").pack(anchor="w")
        ttk.Label(source_options, text="Artwork source").pack(anchor="w", pady=(14, 4))
        build_provider_combo = ttk.Combobox(source_options, textvariable=self.build_provider_var, values=PROVIDER_VALUES, state="readonly", width=20)
        build_provider_combo.pack(anchor="w")
        build_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_build_source_change())
        ttk.Label(source_options, text="Artwork type").pack(anchor="w", pady=(14, 4))
        source_combo = ttk.Combobox(source_options, textvariable=self.build_libretro_source_var, values=list(LIBRETRO_SOURCE_FOLDERS), state="readonly", width=20)
        source_combo.pack(anchor="w")
        source_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_build_source_change())
        ttk.Label(source_options, text="Local pack").pack(anchor="w", pady=(14, 4))
        ttk.Button(source_options, text="Choose Folder…", command=self.choose_local_pack).pack(anchor="w")
        self.local_pack_label = ttk.Label(source_options, text="No local pack selected", style="Muted.TLabel", wraplength=190)
        self.local_pack_label.pack(anchor="w", pady=(6, 0))
        ttk.Label(source_options, text="Thumbnail size").pack(anchor="w", pady=(14, 4))
        build_size_combo = ttk.Combobox(source_options, textvariable=self.size_var, values=["80x80", "120x80"], state="readonly", width=20)
        build_size_combo.pack(anchor="w")
        build_size_combo.bind("<<ComboboxSelected>>", lambda _event: (self.update_build_preview(), self.update_preview()))
        ttk.Checkbutton(source_options, text="Build exceptions only", variable=self.exceptions_only_var).pack(anchor="w", pady=(14, 0))
        self.build_button = ttk.Button(source_options, text="Build Thumbnail Pack", style="Accent.TButton", command=self.build_pack)
        self.build_button.pack(anchor="w", pady=(22, 0))
        self.cancel_build_button = ttk.Button(source_options, text="Cancel Build", command=self.cancel_build)
        self.cancel_build_button.pack(anchor="w", pady=(8, 0))
        self.cancel_build_button.pack_forget()

        ttk.Label(region_options, text="Regions", style="Section.TLabel").pack(anchor="w")
        ttk.Label(region_options, text="Game regions").pack(anchor="w", pady=(14, 4))
        ttk.Label(region_options, text="Choose regions to include in the pack.", style="Muted.TLabel", wraplength=210).pack(anchor="w", pady=(0, 6))
        self._build_rom_region_control(region_options)
        ttk.Label(region_options, text="Artwork priority").pack(anchor="w", pady=(14, 4))
        ttk.Label(region_options, text="Artwork is tried in order when a region has no match.", style="Muted.TLabel", wraplength=210).pack(anchor="w", pady=(0, 6))
        self._build_region_order_control(region_options, scope="build")

        middle = ttk.Frame(self.build_tab, style="Panel.TFrame")
        middle.pack(side="left", fill="y", padx=(0, 18))
        ttk.Label(middle, text="Preview", style="Section.TLabel").pack(anchor="w")
        self.build_preview_label = tk.Label(middle, bg="#101a29", fg="#aebfd2", text="Loading preview…", width=42, height=12, font=("Segoe UI", 10))
        self.build_preview_label.pack(anchor="w", pady=(10, 8))
        self.build_preview_info = ttk.Label(middle, text="Loading preview…", style="Muted.TLabel", wraplength=280)
        self.build_preview_info.pack(anchor="w")
        self.build_preview_loading = ttk.Progressbar(middle, mode="indeterminate", length=180)
        self.build_preview_loading.pack(anchor="w", pady=(6, 0))
        self.build_preview_loading.pack_forget()
        self._build_preview_spinner_running = False
        self.build_pack_crop_label = ttk.Label(middle, text="Preview Crop", style="Section.TLabel")
        self.build_pack_crop_label.pack(anchor="w", pady=(16, 6))
        for label, var, from_, to in (("Zoom", self.build_zoom_var, 1.0, 3.0), ("Move X", self.build_crop_x_var, -100, 100), ("Move Y", self.build_crop_y_var, -100, 100)):
            ttk.Label(middle, text=label).pack(anchor="w")
            tk.Scale(middle, variable=var, from_=from_, to=to, resolution=0.05 if label == "Zoom" else 1, orient="horizontal", bg="#152235", fg="#edf4fb", troughcolor="#101a29", activebackground="#263a57", highlightthickness=0, command=lambda _v: self.update_build_preview()).pack(fill="x")
        ttk.Button(middle, text="Refresh Preview", command=self.build_preview_search).pack(anchor="w", pady=(10, 0))

        right = ttk.Frame(self.build_tab, style="Panel.TFrame")
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Build Progress", style="Section.TLabel").pack(anchor="w")
        self.build_progress = ttk.Progressbar(right, mode="determinate", maximum=100, variable=self.build_progress_var)
        self.build_progress.pack(fill="x", pady=(14, 10))
        self.build_progress.pack_forget()
        self.build_status_label = ttk.Label(right, textvariable=self.build_status_var, style="Muted.TLabel", wraplength=420)
        self.build_status_label.pack(anchor="w")
        self.build_output_label = ttk.Label(right, textvariable=self.build_output_var, style="Muted.TLabel", wraplength=420)
        self.build_output_label.pack(anchor="w", pady=(18, 0))

    def _build_preview_tab(self):
        self.preview_tab.columnconfigure(1, weight=1)
        controls = ttk.Frame(self.preview_tab, style="Panel.TFrame")
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 24))
        ttk.Label(controls, text="Search", style="Section.TLabel").pack(anchor="w")
        ttk.Label(controls, text="Artwork source").pack(anchor="w", pady=(10, 4))
        preview_provider_combo = ttk.Combobox(controls, textvariable=self.preview_provider_var, values=PROVIDER_VALUES, state="readonly", width=24)
        preview_provider_combo.pack(anchor="w")
        preview_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_preview_source_change())
        ttk.Label(controls, text="System").pack(anchor="w", pady=(12, 4))
        self.preview_system_combo = ttk.Combobox(
            controls,
            textvariable=self.preview_system_var,
            values=list(LIBRETRO_SYSTEMS),
            state="readonly",
            width=24,
        )
        self.preview_system_combo.pack(anchor="w")
        self.preview_system_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_preview_system_change())
        ttk.Label(controls, text="Artwork type").pack(anchor="w", pady=(12, 4))
        preview_source_combo = ttk.Combobox(controls, textvariable=self.preview_libretro_source_var, values=list(LIBRETRO_SOURCE_FOLDERS), state="readonly", width=24)
        preview_source_combo.pack(anchor="w")
        preview_source_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_preview_source_change())
        ttk.Button(controls, text="Choose Local Pack…", command=self.choose_local_pack).pack(anchor="w", pady=(10, 0))
        ttk.Label(controls, text="Thumbnail size").pack(anchor="w", pady=(12, 4))
        size_combo = ttk.Combobox(controls, textvariable=self.size_var, values=["80x80", "120x80"], state="readonly", width=24)
        size_combo.pack(anchor="w")
        size_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())
        ttk.Label(controls, text="Artwork priority").pack(anchor="w", pady=(12, 4))
        ttk.Label(controls, text="Set the order of artwork results.", style="Muted.TLabel", wraplength=210).pack(anchor="w", pady=(0, 6))
        self._build_region_order_control(controls, scope="preview")
        ttk.Label(controls, text="Game").pack(anchor="w", pady=(12, 4))
        self.search_entry = ttk.Entry(controls, textvariable=self.search_var, width=34)
        self.search_entry.pack(anchor="w", pady=(10, 4))
        self.search_entry.bind("<KeyRelease>", self.update_suggestions)
        ttk.Label(controls, text="Games without artwork matches").pack(anchor="w", pady=(10, 4))
        self.sd_scan_game_var = tk.StringVar(value="")
        self.sd_scan_game_combo = ttk.Combobox(
            controls, textvariable=self.sd_scan_game_var, state="readonly", width=34,
        )
        self.sd_scan_game_combo.pack(anchor="w")
        self.sd_scan_game_combo.bind("<<ComboboxSelected>>", self.choose_sd_scan_game)
        self.import_sd_scan_report_button = ttk.Button(
            controls, text="Import Scan Report…", command=self.import_sd_scan_report,
        )
        self.import_sd_scan_report_button.pack(anchor="w", pady=(4, 0))
        self.clear_sd_scan_games_button = ttk.Button(
            controls, text="Clear Unmatched Games", command=self.clear_sd_scan_games,
        )
        self.clear_sd_scan_games_button.pack(anchor="w", pady=(4, 0))
        self.clear_sd_scan_games_button.configure(state="disabled")
        self.search_entry.bind("<KeyPress>", self.clear_active_sd_scan_game, add="+")
        self.suggestion_box = tk.Listbox(
            controls,
            height=6,
            width=40,
            bg="#101a29",
            fg="#edf4fb",
            selectbackground="#263e5d",
            selectforeground="#ffffff",
            activestyle="none",
            relief="flat",
            font=("Segoe UI", 9),
        )
        self.suggestion_box.bind("<<ListboxSelect>>", self.choose_suggestion)
        self.suggestion_box.bind("<Return>", self.choose_suggestion)
        self.search_button = ttk.Button(controls, text="Search Artwork", style="Accent.TButton", command=self.preview_search)
        self.search_button.pack(anchor="w")
        ttk.Label(controls, text="Artwork").pack(anchor="w", pady=(12, 4))
        ttk.Button(controls, text="Use Local Image…", command=self.choose_preview_local).pack(anchor="w", pady=(8, 0))
        self.add_to_custom_button = ttk.Button(controls, text="Add to Custom Art", command=self.add_preview_to_custom)
        self.add_to_custom_button.pack(anchor="w", pady=(8, 0))
        self.add_exception_button = ttk.Button(controls, text="Add GBA Exception", command=self.add_exception)
        self.add_exception_button.pack(anchor="w", pady=(8, 0))

        preview = ttk.Frame(self.preview_tab, style="Panel.TFrame")
        preview.grid(row=0, column=1, sticky="nsew", padx=(0, 20))
        ttk.Label(preview, text="Preview", style="Section.TLabel").pack(anchor="w")
        self.preview_label = tk.Label(preview, bg="#101a29", width=420, height=300)
        self.preview_label.pack(pady=(12, 0), anchor="nw")
        self.preview_info = ttk.Label(preview, text="", style="Muted.TLabel")
        self.preview_info.pack(anchor="w", pady=(10, 0))
        ttk.Label(preview, text="Crop", style="Section.TLabel").pack(anchor="w", pady=(16, 8))
        crop_grid = ttk.Frame(preview, style="Panel.TFrame")
        crop_grid.pack(fill="x", anchor="w")
        for col, (label, var, from_, to) in enumerate((("Zoom", self.zoom_var, 1.0, 3.0), ("Move X", self.crop_x_var, -100, 100), ("Move Y", self.crop_y_var, -100, 100))):
            box = ttk.Frame(crop_grid, style="Panel.TFrame")
            box.grid(row=0, column=col, sticky="ew", padx=(0, 14))
            crop_grid.columnconfigure(col, weight=1)
            ttk.Label(box, text=label).pack(anchor="w")
            tk.Scale(box, variable=var, from_=from_, to=to, resolution=0.05 if label == "Zoom" else 1, orient="horizontal", bg="#152235", fg="#edf4fb", troughcolor="#101a29", activebackground="#263a57", highlightthickness=0, command=lambda _v: self.update_preview()).pack(fill="x")
        self.preview_loading = ttk.Progressbar(preview, mode="indeterminate", length=240)
        self.preview_loading.pack(anchor="w", pady=(10, 0))
        self.preview_loading.pack_forget()
        results = ttk.Frame(self.preview_tab, style="Panel.TFrame", width=360)
        results.grid(row=0, column=2, sticky="nsw")
        results.grid_propagate(False)
        ttk.Label(results, text="Search Results", style="Section.TLabel").pack(anchor="w")
        gallery_box = tk.Frame(results, bg="#152235", highlightthickness=0, bd=0)
        gallery_box.pack(fill="both", expand=True, anchor="w", pady=(12, 0))
        gallery_box.rowconfigure(0, weight=1)
        gallery_box.columnconfigure(0, weight=1)
        self.gallery_canvas = tk.Canvas(gallery_box, bg="#152235", highlightthickness=0, bd=0)
        self.gallery_frame = ttk.Frame(self.gallery_canvas, style="Panel.TFrame")
        self.gallery_window = self.gallery_canvas.create_window((0, 0), window=self.gallery_frame, anchor="nw")
        self.gallery_ybar = ttk.Scrollbar(gallery_box, orient="vertical", command=self.gallery_canvas.yview)
        self.gallery_canvas.configure(yscrollcommand=self._set_gallery_scrollbar)
        self.gallery_canvas.grid(row=0, column=0, sticky="nsew")
        self.gallery_ybar.grid(row=0, column=1, sticky="ns")
        self.gallery_ybar.grid_remove()
        self.gallery_frame.bind("<Configure>", self._sync_gallery_scroll_area)
        self.gallery_canvas.bind("<Configure>", self._sync_gallery_canvas_width)
        self.gallery_canvas.bind("<Enter>", self._enable_gallery_mousewheel)
        self.gallery_canvas.bind("<Leave>", self._disable_gallery_mousewheel)

    def _build_custom_tab(self):
        self.custom_tab.columnconfigure(0, weight=1)
        self.custom_tab.rowconfigure(2, weight=1)
        ttk.Label(self.custom_tab, text="Artwork Entries", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.custom_tab,
            text="Add artwork for games on your SD card. Mirrored folders preserve ROM paths; Legacy CUSTOM uses a flat folder. ROM files are never changed.",
            style="Muted.TLabel",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(8, 14))

        body = ttk.Frame(self.custom_tab, style="Panel.TFrame")
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1, minsize=470)
        body.columnconfigure(1, weight=0, minsize=175)
        body.columnconfigure(2, weight=0, minsize=340)
        body.rowconfigure(0, weight=1)

        list_area = ttk.Frame(body, style="Panel.TFrame")
        list_area.grid(row=0, column=0, sticky="nsew", padx=(0, 24))
        list_area.rowconfigure(0, weight=1)
        list_area.columnconfigure(0, weight=1)
        self.custom_tree = ttk.Treeview(list_area, columns=("name", "source", "size", "image"), show="headings", height=11, selectmode="extended")
        for column, text, width in (("name", "Artwork name", 230), ("source", "System", 120), ("size", "Size", 76), ("image", "Image", 170)):
            self.custom_tree.heading(column, text=text)
            self.custom_tree.column(column, width=width, stretch=True)
        custom_ybar = ttk.Scrollbar(list_area, orient="vertical", command=self.custom_tree.yview)
        self.custom_tree.configure(yscrollcommand=custom_ybar.set)
        self.custom_tree.grid(row=0, column=0, sticky="nsew")
        custom_ybar.grid(row=0, column=1, sticky="ns")
        custom_ybar.grid_remove()
        self._sync_tree_columns(self.custom_tree, {"name": 0.42, "source": 0.20, "size": 0.14, "image": 0.24})
        self.custom_scroll_sync = self._sync_tree_scrollbar(self.custom_tree, custom_ybar)
        self.custom_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_custom_selection_changed())
        self.custom_tree.bind("<Button-1>", self.on_custom_tree_click, add="+")
        def scroll_custom_tree(event):
            self.custom_tree.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        self.custom_tree.bind("<MouseWheel>", scroll_custom_tree)

        actions = ttk.Frame(body, style="Panel.TFrame")
        actions.grid(row=0, column=1, sticky="n", padx=(0, 24))
        self.scan_sd_button = ttk.Button(actions, text="Scan SD Card…", style="Accent.TButton", command=self.scan_sd_card)
        self.scan_sd_button.pack(anchor="w", fill="x", pady=(0, 12))
        ttk.Button(actions, text="Add ROMs…", command=self.add_custom_roms).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Button(actions, text="Add Name…", command=self.add_custom_name).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Button(actions, text="Set Image…", command=self.set_custom_image).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Button(actions, text="Remove Selected", command=self.remove_custom_roms).pack(anchor="w", fill="x", pady=(0, 16))
        ttk.Label(actions, text="Thumbnail size").pack(anchor="w")
        custom_size_combo = ttk.Combobox(actions, textvariable=self.size_var, values=["80x80", "120x80"], state="readonly", width=18)
        custom_size_combo.pack(anchor="w", fill="x", pady=(4, 12))
        custom_size_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_custom_size_to_selection())
        ttk.Label(actions, text="Name (Legacy CUSTOM)").pack(anchor="w")
        self.custom_code_var = tk.StringVar()
        ttk.Entry(actions, textvariable=self.custom_code_var, width=22).pack(anchor="w", fill="x", pady=(4, 8))
        ttk.Label(actions, text="Mirrored artwork uses the ROM filename and folder path.", style="Muted.TLabel", wraplength=170).pack(anchor="w", pady=(0, 4))
        ttk.Label(actions, text="Output layout").pack(anchor="w")
        custom_layout_combo = ttk.Combobox(
            actions,
            textvariable=self.custom_output_layout_var,
            values=["Mirror ROM folders", "Legacy CUSTOM"],
            state="readonly",
            width=18,
        )
        custom_layout_combo.pack(anchor="w", fill="x", pady=(4, 5))
        custom_layout_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_custom_output_layout_changed())
        ttk.Label(
            actions,
            text="Mirror ROM folders to avoid the 256-image limit. System defaults (gb.bmp, nes.bmp) stay in CUSTOM.",
            style="Muted.TLabel",
            wraplength=170,
        ).pack(anchor="w", pady=(0, 8))
        ttk.Button(actions, text="Apply Name", command=self.apply_custom_code).pack(anchor="w", fill="x", pady=(0, 16))

        right = ttk.Frame(body, style="Panel.TFrame")
        right.grid(row=0, column=2, sticky="nw")
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Entry Preview", style="Section.TLabel").pack(anchor="w")
        self.custom_preview_label = tk.Label(right, bg="#101a29", width=300, height=210)
        self.custom_preview_label.pack_propagate(False)
        self.custom_preview_label.pack(anchor="w", pady=(8, 6))
        self.custom_preview_info = ttk.Label(right, text="Select an entry to preview its image.", style="Muted.TLabel", wraplength=340)
        self.custom_preview_info.pack(anchor="w")
        crop_row = ttk.Frame(right, style="Panel.TFrame")
        crop_row.pack(anchor="w", pady=(12, 0))
        for label, var, from_, to in (("Zoom", self.custom_zoom_var, 1.0, 3.0), ("Move X", self.custom_crop_x_var, -100, 100), ("Move Y", self.custom_crop_y_var, -100, 100)):
            control = ttk.Frame(crop_row, style="Panel.TFrame")
            control.pack(side="left", padx=(0, 10))
            ttk.Label(control, text=label).pack(anchor="w")
            tk.Scale(control, variable=var, from_=from_, to=to, resolution=0.05 if label == "Zoom" else 1, orient="horizontal", length=120, bg="#152235", fg="#edf4fb", troughcolor="#101a29", activebackground="#263a57", highlightthickness=0, command=lambda _v: self.on_custom_crop_changed()).pack(anchor="w")

        custom_footer = ttk.Frame(self.custom_tab, style="Panel.TFrame")
        custom_footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.build_custom_art_button = ttk.Button(
            custom_footer,
            text="Build Art Pack",
            style="Accent.TButton",
            command=self.build_custom_rom_output,
        )
        self.build_custom_art_button.pack(side="left")

    def _build_exceptions_tab(self):
        ttk.Label(self.exceptions_tab, text="Per-game Exceptions", style="Section.TLabel").pack(anchor="w")
        tree_box = tk.Frame(self.exceptions_tab, bg="#152235", highlightthickness=0, bd=0)
        tree_box.pack(fill="both", expand=True, anchor="w", pady=(12, 8))
        tree_box.rowconfigure(0, weight=1)
        tree_box.columnconfigure(0, weight=1)
        self.exception_tree = ttk.Treeview(tree_box, columns=("title", "size", "provider", "label"), show="headings", height=14, selectmode="extended")
        for column, text, width in (("title", "Game", 240), ("size", "Size", 70), ("provider", "Source", 105), ("label", "Artwork", 300)):
            self.exception_tree.heading(column, text=text)
            self.exception_tree.column(column, width=width, stretch=True)
        exception_ybar = ttk.Scrollbar(tree_box, orient="vertical", command=self.exception_tree.yview)
        self.exception_tree.configure(yscrollcommand=exception_ybar.set)
        self.exception_tree.grid(row=0, column=0, sticky="nsew")
        exception_ybar.grid(row=0, column=1, sticky="ns")
        exception_ybar.grid_remove()
        self._sync_tree_columns(self.exception_tree, {"title": 0.34, "size": 0.10, "provider": 0.16, "label": 0.40})
        self.exception_scroll_sync = self._sync_tree_scrollbar(self.exception_tree, exception_ybar)
        ttk.Button(self.exceptions_tab, text="Remove Selected", command=self.remove_exception).pack(anchor="w")

    def _build_settings_tab(self):
        ttk.Label(self.settings_tab, text="Provider Credentials", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        fields = [
            ("Local pack folder", self.local_pack_var, "folder", False),
            ("IGDB Client ID", self.igdb_client_var, None, False),
            ("IGDB Client Secret", self.igdb_secret_var, "igdb_secret", True),
            ("TheGamesDB API key", self.tgdb_key_var, "thegamesdb", True),
            ("ScreenScraper developer ID", self.ss_dev_id_var, "screenscraper", False),
            ("ScreenScraper developer password", self.ss_dev_pass_var, "ss_dev_pass", True),
            ("ScreenScraper username (optional)", self.ss_user_var, None, False),
            ("ScreenScraper password (optional)", self.ss_pass_var, "ss_pass", True),
        ]
        for field_index, (label, var, action, hidden) in enumerate(fields):
            row = field_index + 1 + (1 if field_index else 0)
            ttk.Label(self.settings_tab, text=label).grid(row=row, column=0, sticky="w", pady=6)
            if action == "folder":
                ttk.Entry(self.settings_tab, textvariable=var, width=54).grid(
                    row=row, column=1, sticky="w", padx=(10, 8)
                )
                ttk.Button(self.settings_tab, text="Browse", command=self.choose_local_pack).grid(
                    row=row, column=2, sticky="w"
                )
                ttk.Checkbutton(
                    self.settings_tab,
                    text="Prefer local-pack matches over cached or online artwork",
                    variable=self.local_pack_priority_var,
                    command=self.save_settings,
                ).grid(row=row + 1, column=1, columnspan=2, sticky="w", padx=(10, 8), pady=(0, 6))
            elif action in {"thegamesdb", "igdb_secret", "ss_dev_pass", "ss_pass"}:
                controls = ttk.Frame(self.settings_tab, style="Panel.TFrame")
                controls.grid(row=row, column=1, sticky="w", padx=(10, 8))
                entry = ttk.Entry(controls, textvariable=var, width=38, show="*" if hidden else "")
                entry.pack(side="left")
                reveal = ttk.Button(controls, text="Show", width=7)
                reveal.pack(side="left", padx=(6, 0))
                if action == "thegamesdb":
                    self.tgdb_key_entry = entry
                    self.tgdb_key_reveal_button = reveal
                    reveal.configure(command=self.toggle_tgdb_key_visibility)
                    self.tgdb_test_button = ttk.Button(
                        self.settings_tab, text="Test Key", command=self.test_thegamesdb_key
                    )
                    self.tgdb_test_button.grid(row=row, column=2, sticky="w")
                elif action == "igdb_secret":
                    self.igdb_secret_entry = entry
                    self.igdb_secret_reveal_button = reveal
                    reveal.configure(command=self.toggle_igdb_secret_visibility)
                    self.igdb_test_button = ttk.Button(
                        self.settings_tab, text="Test Credentials", command=self.test_igdb_credentials_gui
                    )
                    self.igdb_test_button.grid(row=row, column=2, sticky="w")
                elif action == "ss_dev_pass":
                    self.ss_dev_pass_entry = entry
                    self.ss_dev_pass_reveal_button = reveal
                    reveal.configure(command=self.toggle_ss_dev_pass_visibility)
                else:
                    self.ss_pass_entry = entry
                    self.ss_pass_reveal_button = reveal
                    reveal.configure(command=self.toggle_ss_pass_visibility)
            else:
                ttk.Entry(self.settings_tab, textvariable=var, width=54, show="*" if hidden else "").grid(
                    row=row, column=1, sticky="w", padx=(10, 8)
                )
                if action == "screenscraper":
                    self.ss_test_button = ttk.Button(
                        self.settings_tab, text="Test Credentials", command=self.test_screenscraper_credentials_gui
                    )
                    self.ss_test_button.grid(row=row, column=2, sticky="w")

        help_row = len(fields) + 2
        ttk.Label(
            self.settings_tab,
            text=(
                "Fallback order: Libretro → TheGamesDB → ScreenScraper → IGDB. "
                "IGDB uses your Twitch Client ID and Secret; the app handles access tokens. "
                "ScreenScraper requires developer credentials. Account username and password are optional, but must be entered together. "
                "Providers without valid credentials or a matching system are skipped."
            ),
            style="Muted.TLabel",
            wraplength=700,
        ).grid(row=help_row, column=1, columnspan=2, sticky="w", pady=(8, 0), padx=(10, 8))
        actions = ttk.Frame(self.settings_tab, style="Panel.TFrame")
        actions.grid(row=help_row + 1, column=1, columnspan=2, sticky="w", pady=(16, 0), padx=(10, 8))
        ttk.Button(
            actions,
            text="Get TheGamesDB API key",
            command=lambda: webbrowser.open("https://thegamesdb.net/?tab=api"),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions,
            text="Get IGDB credentials",
            command=lambda: webbrowser.open("https://dev.twitch.tv/console/apps"),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions,
            text="ScreenScraper API access",
            command=lambda: webbrowser.open("https://www.screenscraper.fr/webapi2.php"),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save Settings", style="Accent.TButton", command=self.save_settings).pack(side="left")

    def toggle_tgdb_key_visibility(self):
        if not self.tgdb_key_entry or not self.tgdb_key_reveal_button:
            return
        self.tgdb_key_visible = not self.tgdb_key_visible
        self.tgdb_key_entry.configure(show="" if self.tgdb_key_visible else "*")
        self.tgdb_key_reveal_button.configure(text="Hide" if self.tgdb_key_visible else "Show")

    def toggle_igdb_secret_visibility(self):
        if not self.igdb_secret_entry or not self.igdb_secret_reveal_button:
            return
        self.igdb_secret_visible = not self.igdb_secret_visible
        self.igdb_secret_entry.configure(show="" if self.igdb_secret_visible else "*")
        self.igdb_secret_reveal_button.configure(text="Hide" if self.igdb_secret_visible else "Show")

    def toggle_ss_dev_pass_visibility(self):
        if not self.ss_dev_pass_entry or not self.ss_dev_pass_reveal_button:
            return
        self.ss_dev_pass_visible = not self.ss_dev_pass_visible
        self.ss_dev_pass_entry.configure(show="" if self.ss_dev_pass_visible else "*")
        self.ss_dev_pass_reveal_button.configure(text="Hide" if self.ss_dev_pass_visible else "Show")

    def toggle_ss_pass_visibility(self):
        if not self.ss_pass_entry or not self.ss_pass_reveal_button:
            return
        self.ss_pass_visible = not self.ss_pass_visible
        self.ss_pass_entry.configure(show="" if self.ss_pass_visible else "*")
        self.ss_pass_reveal_button.configure(text="Hide" if self.ss_pass_visible else "Show")

    def test_thegamesdb_key(self):
        if self.tgdb_test_progress_window is not None:
            return
        api_key = self.tgdb_key_var.get().strip()
        if not api_key:
            messagebox.showinfo(APP_NAME, "Enter your TheGamesDB API key first.")
            return
        try:
            self.save_settings()
        except OSError as exc:
            messagebox.showwarning(APP_NAME, f"Could not save settings before testing the key:\n{exc}")
            return
        self.tgdb_test_button.configure(state="disabled")
        self.tgdb_test_progress_window = OperationProgressWindow(
            self, "Test TheGamesDB API Key", "Contacting TheGamesDB to verify the key…"
        )

        def worker():
            try:
                platform_count = self.providers.test_thegamesdb_api_key(api_key)
                self.after(0, lambda count=platform_count: self.finish_thegamesdb_key_test(count, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self.finish_thegamesdb_key_test(0, error))

        threading.Thread(target=worker, daemon=True).start()

    def finish_thegamesdb_key_test(self, platform_count: int, error: Exception | None):
        self.close_operation_progress("tgdb_test_progress_window")
        if self.tgdb_test_button:
            self.tgdb_test_button.configure(state="normal")
        if error is None:
            self.status_var.set("TheGamesDB API key verified.")
            messagebox.showinfo(APP_NAME, f"TheGamesDB API key works. Retrieved {platform_count} platforms.")
        else:
            self.status_var.set("TheGamesDB API key test failed.")
            messagebox.showwarning(APP_NAME, f"Could not verify TheGamesDB API key:\n{error}")

    def test_igdb_credentials_gui(self):
        if self.igdb_test_progress_window is not None:
            return
        if not self.igdb_client_var.get().strip() or not self.igdb_secret_var.get().strip():
            messagebox.showinfo(APP_NAME, "Enter your IGDB/Twitch Client ID and Client Secret first.")
            return
        self._start_provider_credential_test(
            "IGDB",
            "igdb_test_progress_window",
            self.igdb_test_button,
            self.providers.test_igdb_credentials,
        )

    def test_screenscraper_credentials_gui(self):
        if self.ss_test_progress_window is not None:
            return
        if not self.ss_dev_id_var.get().strip() or not self.ss_dev_pass_var.get().strip():
            messagebox.showinfo(APP_NAME, "Enter your ScreenScraper developer ID and developer password first.")
            return
        self._start_provider_credential_test(
            "ScreenScraper",
            "ss_test_progress_window",
            self.ss_test_button,
            self.providers.test_screenscraper_credentials,
        )

    def _start_provider_credential_test(self, provider_name, window_attribute, button, test_call):
        try:
            self.save_settings()
        except OSError as exc:
            messagebox.showwarning(APP_NAME, f"Could not save settings before testing {provider_name}:\n{exc}")
            return
        if button is not None:
            button.configure(state="disabled")
        setattr(
            self,
            window_attribute,
            OperationProgressWindow(self, f"Test {provider_name} Credentials", f"Contacting {provider_name}…"),
        )

        def worker():
            try:
                count = test_call()
                self.after(0, lambda count=count: self.finish_provider_credential_test(
                    provider_name, window_attribute, button, count, None
                ))
            except Exception as exc:
                self.after(0, lambda error=exc: self.finish_provider_credential_test(
                    provider_name, window_attribute, button, 0, error
                ))

        threading.Thread(target=worker, daemon=True).start()

    def finish_provider_credential_test(self, provider_name, window_attribute, button, count: int, error: Exception | None):
        self.close_operation_progress(window_attribute)
        if button is not None:
            button.configure(state="normal")
        if error is None:
            self.status_var.set(f"{provider_name} credentials verified.")
            messagebox.showinfo(APP_NAME, f"{provider_name} credentials work. Retrieved {count} platform/system records.")
        else:
            self.status_var.set(f"{provider_name} credential test failed.")
            messagebox.showwarning(APP_NAME, f"Could not verify {provider_name} credentials:\n{error}")

    def log(self, text: str):
        self.status_var.set(text)
        self.update_idletasks()

    def queue_operation_progress(
        self,
        window_attribute: str,
        heading: str,
        current: int | None = None,
        total: int | None = None,
        detail: str = "",
    ):
        """Queue progress updates from worker threads onto Tk's main thread."""
        def update():
            window = getattr(self, window_attribute, None)
            if window is not None:
                window.update_progress(heading, current, total, detail)
            self.status_var.set(f"{heading} — {detail}" if detail else heading)

        try:
            self.after(0, update)
        except tk.TclError:
            pass

    def close_operation_progress(self, window_attribute: str):
        window = getattr(self, window_attribute, None)
        if window is not None:
            window.close()
            setattr(self, window_attribute, None)

    def set_build_progress(self, value: float | None = None, text: str | None = None, output: str | None = None):
        def update():
            if hasattr(self, "build_progress"):
                if self.running:
                    if not self.build_progress.winfo_ismapped():
                        self.build_progress.pack(fill="x", pady=(14, 10), before=self.build_status_label)
                else:
                    self.build_progress.pack_forget()
            if value is not None:
                self.build_progress_var.set(value)
            if text is not None:
                self.build_status_var.set(text)
                self.status_var.set(text)
            if output is not None:
                self.build_output_var.set(output)
        self.after(0, update)

    def selected_size(self) -> tuple[int, int, str]:
        return self.size_details(self.size_var.get())

    def size_details(self, size: str) -> tuple[int, int, str]:
        if size == "120x80":
            return 120, 80, "IMGS"
        return 80, 80, "IMGS2"

    def refresh_region_lists(self):
        for region_list in self.region_listboxes:
            selected = region_list.curselection()
            region_list.delete(0, "end")
            for region in self.region_order:
                marker = "[x]" if self.region_enabled.get(region, True) else "[ ]"
                region_list.insert("end", f"{marker} {region}")
            if selected:
                region_list.selection_set(min(selected[0], len(self.region_order) - 1))

    def move_region(self, region_list: tk.Listbox, direction: int, scope: str = "build"):
        selection = region_list.curselection()
        if not selection:
            return
        index = selection[0]
        new_index = index + direction
        if new_index < 0 or new_index >= len(self.region_order):
            return
        self.region_order[index], self.region_order[new_index] = self.region_order[new_index], self.region_order[index]
        self.refresh_region_lists()
        for listbox in self.region_listboxes:
            listbox.selection_clear(0, "end")
            listbox.selection_set(new_index)
        self._schedule_settings_save()
        self.on_region_change(scope=scope, update_suggestions=False)

    def toggle_region(self, region_list: tk.Listbox, scope: str = "build"):
        selection = region_list.curselection()
        if not selection:
            return "break"
        index = selection[0]
        region = self.region_order[index]
        self.region_enabled[region] = not self.region_enabled.get(region, True)
        self.refresh_region_lists()
        for listbox in self.region_listboxes:
            listbox.selection_clear(0, "end")
            listbox.selection_set(index)
        self._schedule_settings_save()
        self.on_region_change(scope=scope, update_suggestions=True)
        return "break"

    def selected_regions(self) -> set[str]:
        return {region for region in self.region_order if self.region_enabled.get(region, True)}

    def ordered_regions(self) -> list[str]:
        return [region for region in self.region_order if self.region_enabled.get(region, True)]

    def selected_rom_regions(self) -> set[str]:
        return {region for region, var in self.rom_region_vars.items() if var.get()}

    def region_allowed(self, title: str) -> bool:
        allowed = self.selected_regions()
        return bool(allowed and title_regions(title) & allowed)

    def region_priority(self, title: str) -> int:
        regions = title_regions(title)
        for index, region in enumerate(self.ordered_regions()):
            if region in regions:
                return index
        return len(self.ordered_regions())

    def display_region_for(self, title: str) -> str:
        regions = title_regions(title)
        for region in self.ordered_regions():
            if region in regions:
                return region
        return "Other"

    def build_preview_queries(self) -> list[str]:
        queries: list[str] = []
        for region in self.ordered_regions():
            queries.extend(BUILD_PREVIEW_SAMPLES[region])
        return list(dict.fromkeys(queries or [DEFAULT_SEARCH]))

    def on_region_change(self, scope: str = "build", update_suggestions: bool = False):
        """React locally to region edits; do not fire provider requests from both tabs."""
        if scope == "preview":
            if update_suggestions:
                self.hide_suggestions()
                self._schedule_suggestion_refresh()
            if self.result_options:
                self._schedule_preview_gallery_refresh()
            else:
                self.status_var.set("Artwork priority updated. Search again to see results in this order.")
            return
        self._schedule_build_preview_search(delay=650)

    def on_rom_region_change(self):
        # Saving serializes all custom-art entries; debounce rapid checkbox edits so
        # the UI does not repeatedly rewrite a potentially large settings file.
        self._schedule_settings_save()

    def _schedule_settings_save(self, delay: int = 550):
        pending = getattr(self, "_settings_save_after_id", None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self.status_var.set("Saving region settings…")
        self._settings_save_after_id = self.after(delay, self._run_scheduled_settings_save)

    def _run_scheduled_settings_save(self):
        self._settings_save_after_id = None
        try:
            self.save_settings()
        except OSError as exc:
            self.status_var.set(f"Could not save settings: {exc}")

    def _schedule_preview_gallery_refresh(self, delay: int = 220):
        """Coalesce local gallery resorting while the user changes priority quickly."""
        pending = getattr(self, "_preview_gallery_refresh_after_id", None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self.status_var.set("Reordering preview results by artwork priority…")
        self.set_preview_loading(True)
        self._preview_gallery_refresh_after_id = self.after(delay, self._finish_preview_gallery_refresh)

    def _finish_preview_gallery_refresh(self):
        self._preview_gallery_refresh_after_id = None
        try:
            if self.result_options:
                self.refresh_result_gallery()
            else:
                self.status_var.set("Artwork priority updated.")
        finally:
            self.set_preview_loading(False)

    def _schedule_suggestion_refresh(self, delay: int = 180):
        """Debounce local autocomplete filtering while region toggles are changing."""
        pending = getattr(self, "_suggestions_refresh_after_id", None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self._suggestions_refresh_after_id = self.after(delay, self._finish_suggestion_refresh)

    def _finish_suggestion_refresh(self):
        self._suggestions_refresh_after_id = None
        self.update_suggestions()

    def on_build_source_change(self):
        self.save_settings()
        self.build_preview_search()

    def on_preview_source_change(self):
        self.save_settings()
        self.hide_suggestions()
        self._load_system_names_async(self.preview_system_var.get())
        if self.search_var.get().strip():
            self.preview_search()

    def on_preview_system_change(self):
        self.save_settings()
        self.hide_suggestions()
        self._load_system_names_async(self.preview_system_var.get())
        if hasattr(self, "add_exception_button"):
            state = "normal" if self.preview_system_var.get() == DEFAULT_SYSTEM else "disabled"
            self.add_exception_button.configure(state=state)
        if self.search_var.get().strip():
            self.preview_search()

    def on_source_change(self):
        self.on_build_source_change()
        self.on_preview_source_change()

    def on_tab_changed(self, event):
        notebook = event.widget
        if notebook.tab(notebook.select(), "text") == "Custom Art":
            self.update_custom_preview()

    def update_local_pack_label(self):
        if not hasattr(self, "local_pack_label"):
            return
        path = self.local_pack_var.get().strip()
        self.local_pack_label.configure(text=Path(path).name if path else "No local pack selected")

    def _load_game_names_async(self):
        def worker():
            try:
                cache = self.base_dir / CACHE_FOLDER_NAME / "libretro_nointro_gba_library.json"
                library = load_gba_library(cache)
                names = sorted({entry.title for entry in library}, key=str.casefold)
                codes = {entry.code for entry in library if entry.code}
                self.after(0, lambda: self._set_game_library(library, names, codes))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _set_game_library(self, library, names: list[str], codes: set[str]):
        self.game_library = library
        self.game_names = names
        self.known_game_codes = codes

    def _load_system_names_async(self, system: str):
        if system == DEFAULT_SYSTEM or system in self.system_game_names:
            return
        folder = LIBRETRO_SOURCE_FOLDERS.get(self.preview_libretro_source_var.get(), "Named_Boxarts")

        def worker():
            try:
                index = self.providers.get_libretro_index(system, folder)
                names = sorted({display_libretro_name(name) for name in index}, key=str.casefold)
                self.after(0, lambda: self.system_game_names.setdefault(system, names))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def get_game_library(self):
        if not self.game_library:
            cache = self.base_dir / CACHE_FOLDER_NAME / "libretro_nointro_gba_library.json"
            self.game_library = load_gba_library(cache)
        return self.game_library

    def update_suggestions(self, event=None):
        if event and event.keysym in {"Return", "Escape", "Up", "Down"}:
            if event.keysym == "Escape":
                self.hide_suggestions()
            return
        if not self.suggestion_box:
            return
        query = self.search_var.get().strip().lower()
        system = self.preview_system_var.get()
        names = self.game_names if system == DEFAULT_SYSTEM else self.system_game_names.get(system, [])
        if len(query) < 2 or not names:
            self.hide_suggestions()
            return
        matches = [name for name in names if query in name.lower() and self.region_allowed(name)][:8]
        self.suggestion_box.delete(0, "end")
        for name in matches:
            self.suggestion_box.insert("end", name)
        if matches:
            if not self.suggestion_box.winfo_ismapped():
                self.suggestion_box.pack(anchor="w", pady=(0, 8), before=self.search_button)
        else:
            self.hide_suggestions()

    def choose_suggestion(self, event=None):
        if not self.suggestion_box:
            return
        selection = self.suggestion_box.curselection()
        if not selection:
            return
        self.search_var.set(self.suggestion_box.get(selection[0]))
        self.hide_suggestions()

    def choose_sd_scan_game(self, event=None):
        selection = self.sd_scan_game_combo.current()
        if selection < 0 or selection >= len(self.sd_scan_unmatched_games):
            return
        game = self.sd_scan_unmatched_games[selection]
        self.active_sd_scan_game = game
        self.search_var.set(Path(game["path"]).stem if game.get("path") else Path(game["title"]).stem)
        self.preview_system_var.set(game.get("system") or DEFAULT_SYSTEM)
        self.notebook.select(self.preview_tab)
        self.status_var.set("Search for artwork for this SD card game, then add the result to Custom Art.")

    def clear_sd_scan_games(self):
        self.sd_scan_unmatched_games.clear()
        self.sd_scan_game_combo.configure(values=[])
        self.sd_scan_game_var.set("")
        self.active_sd_scan_game = None
        self.clear_sd_scan_games_button.configure(state="disabled")
        self.status_var.set("Cleared unmatched SD card games.")

    def clear_active_sd_scan_game(self, event=None):
        # Editing the query means the selected queue entry is no longer the search target.
        self.active_sd_scan_game = None

    def import_sd_scan_report(self):
        report_name = filedialog.askopenfilename(
            title="Import SD scan report",
            filetypes=[("SD scan reports", "*.txt"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not report_name:
            return
        report_path = Path(report_name)
        imported: list[dict[str, str]] = []
        metadata_path = report_path.with_suffix(".json")
        if metadata_path.is_file():
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                imported = [
                    {
                        "title": str(item["title"]),
                        "system": str(item.get("system", DEFAULT_SYSTEM)),
                        "path": str(item.get("path", "")),
                        "relative": str(item.get("relative", "")),
                    }
                    for item in payload.get("unmatched_games", [])
                    if isinstance(item, dict) and item.get("title")
                ]
            except (OSError, ValueError, TypeError, KeyError) as exc:
                messagebox.showwarning(APP_NAME, f"Could not read scan report data:\n{exc}", parent=self)
                return
        if not imported:
            try:
                lines = report_path.read_text(encoding="utf-8-sig").splitlines()
            except OSError as exc:
                messagebox.showwarning(APP_NAME, f"Could not read scan report:\n{exc}", parent=self)
                return
            prefix = "No artwork match found for "
            suffix = " on any of the media providers."
            for line in lines:
                line = line.strip()
                if line.startswith(prefix) and line.endswith(suffix):
                    title = line[len(prefix):-len(suffix)]
                    system = SYSTEM_BY_EXTENSION.get(Path(title).suffix.lower(), DEFAULT_SYSTEM)
                    imported.append({"title": title, "system": system, "path": "", "relative": ""})
        if not imported:
            messagebox.showinfo(APP_NAME, "No unmatched game entries were found in that report.", parent=self)
            return
        existing = {
            (item.get("path", "").casefold(), item["title"].casefold(), item.get("system", "").casefold())
            for item in self.sd_scan_unmatched_games
        }
        added = 0
        for game in imported:
            key = (game.get("path", "").casefold(), game["title"].casefold(), game.get("system", "").casefold())
            if key not in existing:
                self.sd_scan_unmatched_games.append(game)
                existing.add(key)
                added += 1
        self.refresh_sd_scan_game_dropdown()
        self.status_var.set(f"Imported {added} unmatched game(s) from the scan report.")

    def refresh_sd_scan_game_dropdown(self):
        self.sd_scan_game_combo.configure(values=[
            f"{Path(game['path']).name if game.get('path') else game['title']} — {game.get('system', DEFAULT_SYSTEM)}"
            for game in self.sd_scan_unmatched_games
        ])
        self.sd_scan_game_var.set("")
        self.clear_sd_scan_games_button.configure(
            state="normal" if self.sd_scan_unmatched_games else "disabled"
        )

    def remove_sd_scan_game_from_queue(self, game: dict[str, str]):
        """Remove a manually searched game while retaining its active add-to-custom context."""
        self.sd_scan_unmatched_games = [
            queued for queued in self.sd_scan_unmatched_games
            if (
                queued.get("path") != game.get("path")
                if game.get("path")
                else not (
                    queued.get("title", "").casefold() == game.get("title", "").casefold()
                    and queued.get("system", "").casefold() == game.get("system", "").casefold()
                )
            )
        ]
        self.refresh_sd_scan_game_dropdown()

    def hide_suggestions(self):
        if self.suggestion_box and self.suggestion_box.winfo_ismapped():
            self.suggestion_box.pack_forget()

    def current_crop(self) -> CropSettings:
        return CropSettings(self.zoom_var.get(), self.crop_x_var.get(), self.crop_y_var.get())

    def build_crop(self) -> CropSettings:
        return CropSettings(self.build_zoom_var.get(), self.build_crop_x_var.get(), self.build_crop_y_var.get())

    def custom_crop(self) -> CropSettings:
        return CropSettings(self.custom_zoom_var.get(), self.custom_crop_x_var.get(), self.custom_crop_y_var.get())

    def crop_from_dict(self, value: dict | None) -> CropSettings:
        if not isinstance(value, dict):
            return CropSettings()
        return CropSettings(
            float(value.get("zoom", 1.0)),
            float(value.get("x", 0.0)),
            float(value.get("y", 0.0)),
        )

    def set_custom_crop_controls(self, crop: CropSettings):
        self.loading_custom_crop = True
        try:
            self.custom_zoom_var.set(crop.zoom)
            self.custom_crop_x_var.set(crop.x)
            self.custom_crop_y_var.set(crop.y)
        finally:
            self.loading_custom_crop = False

    def set_preview_loading(self, loading: bool):
        if not hasattr(self, "preview_loading"):
            return
        if loading:
            if not self.preview_loading.winfo_ismapped():
                self.preview_loading.pack(anchor="w", pady=(10, 0))
            self.preview_loading.start(12)
        else:
            self.preview_loading.stop()
            self.preview_loading.pack_forget()

    def preview_search(self):
        searched_sd_game = self.active_sd_scan_game
        if searched_sd_game:
            self.remove_sd_scan_game_from_queue(searched_sd_game)
        self.current_result = None
        self.set_preview_loading(True)
        # A new query replaces the result set; release gallery image objects from
        # the previous query. Region-priority changes reuse these cached thumbs.
        self._gallery_thumb_cache.clear()
        def worker():
            try:
                self.status_var.set("Searching for artwork…")
                results = self.providers.search_many(
                    self.preview_provider_var.get(),
                    self.search_var.get(),
                    max_results=PREVIEW_RESULT_LIMIT,
                    libretro_source=self.preview_libretro_source_var.get(),
                    system=self.preview_system_var.get(),
                )
                self.result_options = results
                result = results[0]
                image = Image.open(__import__("io").BytesIO(result.image_data))
                self.current_result = result
                self.current_source_image = image
                self.after(0, self.refresh_result_gallery)
            except Exception as exc:
                self.after(0, lambda error=exc: messagebox.showwarning(APP_NAME, str(error)))
                self.status_var.set("Preview failed.")
            finally:
                self.after(0, lambda: self.set_preview_loading(False))
        threading.Thread(target=worker, daemon=True).start()

    def build_preview_search(self):
        """Request a build preview without blocking Tk or allowing request storms."""
        self._schedule_build_preview_search(delay=0)

    def _schedule_build_preview_search(self, delay: int = 650):
        self._build_preview_generation = getattr(self, "_build_preview_generation", 0) + 1
        self._build_preview_pending = True
        pending = getattr(self, "_build_preview_after_id", None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        message = "Region settings changed; waiting to refresh the build preview…" if delay else "Refreshing build preview…"
        self._set_build_preview_loading(True, message)
        self._build_preview_after_id = self.after(delay, self._start_scheduled_build_preview_search)

    def _set_build_preview_loading(self, loading: bool, message: str | None = None):
        if message:
            self.status_var.set(message)
            if hasattr(self, "build_preview_info"):
                self.build_preview_info.configure(text=message)
        progress = getattr(self, "build_preview_loading", None)
        if progress is None:
            return
        if loading:
            if not progress.winfo_ismapped():
                progress.pack(anchor="w", pady=(6, 0), before=self.build_pack_crop_label)
            if not getattr(self, "_build_preview_spinner_running", False):
                progress.start(12)
                self._build_preview_spinner_running = True
        else:
            if getattr(self, "_build_preview_spinner_running", False):
                progress.stop()
                self._build_preview_spinner_running = False
            if progress.winfo_ismapped():
                progress.pack_forget()

    def _start_scheduled_build_preview_search(self):
        self._build_preview_after_id = None
        if getattr(self, "_build_preview_worker_running", False):
            # Let the in-flight request finish; its stale result will be discarded
            # and the most recent pending selection will then run once.
            self._build_preview_pending = True
            return
        if not self.selected_regions():
            self._build_preview_pending = False
            self._set_build_preview_loading(False)
            self.build_preview_info.configure(text="Select at least one region to load the build preview.")
            self.status_var.set("No game regions are enabled.")
            return

        token = self._build_preview_generation
        queries = tuple(self.build_preview_queries())
        provider = self.build_provider_var.get()
        libretro_source = self.build_libretro_source_var.get()
        self._build_preview_pending = False
        self._build_preview_worker_running = True
        selected = ", ".join(self.ordered_regions())
        self._set_build_preview_loading(True, f"Searching {provider} artwork for {selected}…")

        def worker():
            result = None
            last_error: Exception | None = None
            try:
                for query in queries:
                    if token != self._build_preview_generation:
                        break
                    try:
                        result = self.providers.search(
                            provider,
                            query,
                            libretro_source=libretro_source,
                        )
                        break
                    except Exception as exc:
                        last_error = exc
                self.after(0, lambda: self._finish_build_preview_search(token, result, last_error))
            except Exception as exc:
                self.after(0, lambda error=exc: self._finish_build_preview_search(token, None, error))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_build_preview_search(self, token: int, result, error: Exception | None):
        self._build_preview_worker_running = False
        if token != self._build_preview_generation:
            if self._build_preview_pending and self._build_preview_after_id is None:
                self._build_preview_after_id = self.after(0, self._start_scheduled_build_preview_search)
            return

        self._build_preview_pending = False
        self._set_build_preview_loading(False)
        if result is not None:
            try:
                with Image.open(io.BytesIO(result.image_data)) as image:
                    source_image = image.copy()
                self.build_result = result
                self.build_source_image = source_image
                self.update_build_preview()
            except Exception as exc:
                self.build_preview_info.configure(text=f"Could not display build preview: {exc}")
                self.status_var.set("Build preview could not be displayed.")
            return

        detail = str(error or "No build preview artwork found.")
        self.build_preview_info.configure(text=f"Preview unavailable: {detail}")
        self.status_var.set(f"Build preview unavailable: {detail}")

    def refresh_result_gallery(self):
        for child in self.gallery_frame.winfo_children():
            child.destroy()
        self.result_thumbs = []
        grouped: dict[str, list[ProviderResult]] = {}
        for result in self.result_options:
            grouped.setdefault(self.display_region_for(result.label), []).append(result)
        row = 0
        columns = 4
        for region in dict.fromkeys([*self.ordered_regions(), "Other"]):
            results = grouped.get(region, [])
            if not results:
                continue
            ttk.Label(self.gallery_frame, text=region, style="Muted.TLabel").grid(row=row, column=0, columnspan=columns, sticky="w", pady=(0 if row == 0 else 8, 6))
            row += 1
            for index, result in enumerate(results):
                card = ttk.Frame(self.gallery_frame, style="Panel.TFrame")
                card.grid(row=row + index // columns, column=index % columns, sticky="nw", padx=(0, 10), pady=(0, 8))
                try:
                    width, height, _folder = self.selected_size()
                    crop = self.current_crop()
                    cache_key = (
                        id(result), width, height,
                        round(crop.zoom, 4), round(crop.x, 3), round(crop.y, 3),
                    )
                    photo = self._gallery_thumb_cache.get(cache_key)
                    if photo is None:
                        with Image.open(io.BytesIO(result.image_data)) as image:
                            thumb = crop_image(image, (width, height), crop).resize(
                                (72, 72 if height == 80 else 48), Image.Resampling.NEAREST
                            )
                        photo = ImageTk.PhotoImage(thumb)
                        self._gallery_thumb_cache[cache_key] = photo
                    self.result_thumbs.append(photo)
                    label = tk.Label(card, image=photo, bg="#101a29", cursor="hand2")
                    label.pack()
                    label.bind("<Button-1>", lambda _event, selected=result: self.use_selected_result(selected))
                except OSError:
                    continue
                text = result.label[:20] + ("..." if len(result.label) > 20 else "")
                tk.Label(card, text=text, bg="#152235", fg="#aebfd2", font=("Segoe UI", 8), wraplength=80).pack(fill="x")
            row += (len(results) + columns - 1) // columns
        self.gallery_canvas.yview_moveto(0)
        self.after(20, self._sync_gallery_scroll_area)
        self.update_preview()
        self.status_var.set("Preview ready.")

    def use_selected_result(self, result: ProviderResult):
        self.current_result = result
        self.current_source_image = Image.open(__import__("io").BytesIO(result.image_data))
        self.update_preview()

    def choose_preview_local(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")])
        if not path:
            return
        data = Path(path).read_bytes()
        self.current_result = ProviderResult("Local Image", Path(path).name, data, self.preview_system_var.get())
        self.current_local_path = path
        self.result_options = [self.current_result]
        self.current_source_image = Image.open(path)
        self.refresh_result_gallery()

    def cache_provider_result(self, result: ProviderResult, source: str = "manual") -> str:
        if not is_valid_image_data(result.image_data):
            raise ValueError(
                f'The artwork provider returned invalid or incomplete image data for "{result.label}". '
                "Try scanning again or use another artwork source."
            )
        digest = hashlib.sha256(
            f"{result.system}|{source}|{result.label}".encode("utf-8") + result.image_data
        ).hexdigest()[:24]
        cache_dir = self.base_dir / CACHE_FOLDER_NAME / "matched artwork"
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{digest}.png"
        if not path.exists():
            with Image.open(io.BytesIO(result.image_data)) as image:
                image.convert("RGBA").save(path, "PNG")
        return str(path)

    def add_preview_to_custom(self):
        if not self.current_result:
            messagebox.showinfo(APP_NAME, "Search for artwork or choose an image first.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Add to Custom Art")
        dialog.configure(bg="#152235")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        ttk.Label(dialog, text="Exact filename without its extension").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))
        sd_game = self.active_sd_scan_game
        initial_name = (
            Path(sd_game.get("path") or sd_game["title"]).stem if sd_game
            else Path(self.search_var.get().strip()).stem or display_libretro_name(self.current_result.label)
        )
        name_var = tk.StringVar(value=initial_name)
        entry = ttk.Entry(dialog, textvariable=name_var, width=42)
        entry.grid(row=1, column=0, sticky="ew", padx=16)
        ttk.Label(
            dialog,
            text="The artwork name must exactly match the file on the SD card.",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(6, 12))
        buttons = ttk.Frame(dialog, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="e", padx=16, pady=(0, 16))

        def add():
            try:
                name = validate_custom_art_name(name_var.get())
                selected_size = self.size_var.get()
                key = (name.casefold(), selected_size)
                if key in {(item.new_code.casefold(), item.size) for item in self.custom_roms}:
                    raise ValueError("That custom name and size is already in the list.")
                image_path = self.cache_provider_result(
                    self.current_result,
                    self.preview_libretro_source_var.get(),
                )
            except (OSError, ValueError) as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=dialog)
                return
            self.custom_roms.append(
                CustomRomItem(
                    sd_game.get("path", "") if sd_game else "",
                    name,
                    "----",
                    name,
                    image_path=image_path,
                    size=selected_size,
                    system=sd_game.get("system", self.preview_system_var.get()) if sd_game else self.preview_system_var.get(),
                    rom_relative_path=sd_game.get("relative", "") if sd_game else "",
                )
            )
            self.refresh_custom_roms([len(self.custom_roms) - 1])
            self.save_settings()
            self.notebook.select(self.custom_tab)
            self.status_var.set(f"Added {name} to Custom Art.")
            if sd_game:
                self.active_sd_scan_game = None
                self.sd_scan_game_var.set("")
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Add", style="Accent.TButton", command=add).pack(side="right")
        entry.bind("<Return>", lambda _event: add())
        entry.focus_set()

    def custom_art_relative_path(self, item: CustomRomItem) -> str:
        """Return the ROM-relative path used by mirror mode, when available."""
        if item.rom_relative_path:
            return item.rom_relative_path.replace("\\", "/")
        if item.rom_path and item.system:
            try:
                return infer_relative_rom_path(Path(item.rom_path), item.system)
            except (OSError, ValueError):
                return ""
        return ""

    @staticmethod
    def is_extension_default_name(name: str) -> bool:
        """Extension defaults are loaded directly by the kernel, outside its index."""
        supported_extensions = {
            extension.lstrip(".").casefold()
            for extension in SYSTEM_BY_EXTENSION
        }
        return name.casefold() in supported_extensions

    def scan_sd_card(self):
        if self.scan_running:
            return
        selected = filedialog.askdirectory(title="Choose the root of the SD card")
        if not selected:
            return
        root = Path(selected)
        dialog = tk.Toplevel(self)
        dialog.title("Scan SD Card")
        dialog.configure(bg="#152235")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.columnconfigure(0, weight=1)
        ttk.Label(dialog, text="Find artwork for installed games", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 6)
        )
        ttk.Label(
            dialog,
            text=f"SD card: {root}\nChoose the SD card root to preserve the folder paths used by your ROM browser.",
            style="Muted.TLabel",
            wraplength=480,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 14))
        ttk.Label(dialog, text="Artwork type").grid(row=2, column=0, sticky="w", padx=(18, 8), pady=5)
        source_var = tk.StringVar(value="Box Art")
        ttk.Combobox(
            dialog,
            textvariable=source_var,
            values=list(LIBRETRO_SOURCE_FOLDERS),
            state="readonly",
            width=24,
        ).grid(row=2, column=1, sticky="ew", padx=(8, 18), pady=5)
        ttk.Label(dialog, text="Thumbnail sizes").grid(row=3, column=0, sticky="w", padx=(18, 8), pady=5)
        sizes_var = tk.StringVar(value="Wide and square")
        ttk.Combobox(
            dialog,
            textvariable=sizes_var,
            values=["Wide and square", "Wide, 120x80", "Square, 80x80"],
            state="readonly",
            width=24,
        ).grid(row=3, column=1, sticky="ew", padx=(8, 18), pady=5)
        include_gba_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog,
            text="Include Game Boy Advance files",
            variable=include_gba_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=18, pady=(10, 2))
        use_hash_matching_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog,
            text="Use ROM hashes if name searches fail (slower; reads ROM files)",
            variable=use_hash_matching_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=18, pady=(8, 2))
        auto_fallback_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog,
            text="Try fallback providers automatically if artwork cannot be downloaded",
            variable=auto_fallback_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=18, pady=(6, 2))
        ttk.Label(
            dialog,
            text=(
                "Search order: Libretro → TheGamesDB → ScreenScraper → IGDB. "
                "Automatic fallback skips the prompt after a download fails. "
                "ROM hash searches check TheGamesDB and ScreenScraper. "
                "Mirrored artwork follows ROM folders under IMGS and IMGS2."
            ),
            style="Muted.TLabel",
            wraplength=480,
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 14))
        buttons = ttk.Frame(dialog, style="Panel.TFrame")
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", padx=18, pady=(0, 18))

        def begin():
            size_names = {
                "Wide and square": ["120x80", "80x80"],
                "Wide, 120x80": ["120x80"],
                "Square, 80x80": ["80x80"],
            }[sizes_var.get()]
            dialog.destroy()
            self.start_sd_scan(
                root, source_var.get(), size_names, include_gba_var.get(),
                use_hash_matching=use_hash_matching_var.get(),
                auto_fallback=auto_fallback_var.get(),
            )

        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Scan", style="Accent.TButton", command=begin).pack(side="right")

    def start_sd_scan(
        self, root: Path, source: str, size_names: list[str], include_gba: bool,
        use_hash_matching: bool = False, auto_fallback: bool = False,
    ):
        if self.scan_running:
            return
        self.scan_running = True
        self.scan_sd_button.configure(state="disabled")
        self.status_var.set("Scanning the SD card for supported games…")
        self.sd_scan_progress_window = OperationProgressWindow(
            self,
            "Scan SD Card",
            "Scanning folders on the SD card…",
        )

        def report_progress(heading, current=None, total=None, detail=""):
            self.queue_operation_progress(
                "sd_scan_progress_window", heading, current, total, detail
            )

        def worker():
            try:
                result = self._scan_sd_worker(
                    root,
                    source,
                    size_names,
                    include_gba,
                    progress_callback=report_progress,
                    use_hash_matching=use_hash_matching,
                    auto_fallback=auto_fallback,
                )
                self.after(0, lambda: self.finish_sd_scan(result))
            except Exception as exc:
                self.after(0, lambda error=exc: self.fail_sd_scan(error))

        threading.Thread(target=worker, daemon=True).start()

    def supported_files_on_sd(self, root: Path, include_gba: bool, progress_callback=None) -> list[tuple[Path, str]]:
        found: list[tuple[Path, str]] = []
        folders_visited = 0
        for current, directories, filenames in os.walk(root):
            folders_visited += 1
            directories[:] = [
                name
                for name in directories
                if not name.startswith(".") and name.casefold() not in SCAN_EXCLUDED_FOLDERS
            ]
            current_path = Path(current)
            for filename in filenames:
                if filename.startswith("."):
                    continue
                path = current_path / filename
                system = system_for_path(path)
                if not system or (system == DEFAULT_SYSTEM and not include_gba):
                    continue
                if path.name.casefold() in {"ezkernel.bin", "ezkernelnew.bin"}:
                    continue
                found.append((path, system))
            if progress_callback and (folders_visited == 1 or folders_visited % 8 == 0):
                progress_callback(
                    "Scanning SD card folders",
                    None,
                    None,
                    f"Folders visited: {folders_visited:,}; supported ROMs found: {len(found):,}",
                )
        if progress_callback:
            progress_callback(
                "SD card folder scan complete",
                1,
                1,
                f"Found {len(found):,} supported ROM files in {folders_visited:,} folders.",
            )
        return sorted(found, key=lambda item: str(item[0]).casefold())

    def sd_scan_cache_path(self, source_folder: str, system: str, art_name: str) -> Path:
        """Stable on-disk cache path for an artwork source match.

        The key includes the system and provider/art folder so the same title
        can have distinct cached box art, screenshots, and title screens.
        """
        identity = f"{system.casefold()}\0{source_folder.casefold()}\0{art_name.casefold()}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        return self.base_dir / CACHE_FOLDER_NAME / "SD scan artwork" / f"{digest}.png"

    def sd_scan_rom_cache_path(self, source_folder: str, system: str, relative_rom_path: str) -> Path:
        """Return the durable per-ROM source-image cache path.

        This lookup key is available before asking any online artwork provider,
        so a previous scan can reuse a cached image even if a provider is now
        unavailable or the provider's search result ordering has changed.
        """
        identity = (
            f"{system.casefold()}\0{source_folder.casefold()}\0"
            f"{relative_rom_path.replace(chr(92), '/').casefold()}"
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        return self.base_dir / CACHE_FOLDER_NAME / "SD scan ROM artwork" / f"{digest}.png"

    def sd_thumbnail_output_roots(self, root: Path, size: str) -> list[Path]:
        """Return the possible existing output directories for one size.

        Build this list once per scan rather than relisting old build folders for
        every game, which keeps incremental scans responsive for large libraries.
        """
        _width, _height, folder_name = self.size_details(size)
        output_roots = [Path(root) / "SYSTEM" / folder_name, Path(root) / folder_name]
        generated_root = self.base_dir / OUTPUT_FOLDER_NAME
        if generated_root.is_dir():
            try:
                previous_runs = sorted(
                    (entry for entry in generated_root.iterdir() if entry.is_dir()),
                    key=lambda entry: entry.name.casefold(),
                    reverse=True,
                )
            except OSError:
                previous_runs = []
            output_roots.extend(run / folder_name for run in previous_runs)
        return output_roots

    def existing_sd_thumbnail(
        self,
        root: Path,
        relative: str,
        size: str,
        output_roots: list[Path] | None = None,
    ) -> Path | None:
        """Find an already-built mirrored thumbnail on the SD or in prior output."""
        width, height, _folder_name = self.size_details(size)
        if output_roots is None:
            output_roots = self.sd_thumbnail_output_roots(root, size)

        checked: set[str] = set()
        for output_root in output_roots:
            try:
                candidate = mirrored_thumbnail_path(output_root, relative)
            except ValueError:
                continue
            identity = str(candidate).casefold()
            if identity in checked:
                continue
            checked.add(identity)
            if is_valid_image_file(candidate, (width, height)):
                return candidate
        return None

    def cache_sd_scan_image(self, cache_path: Path, data: bytes, overwrite: bool = False) -> str:
        """Persist a validated provider response as a reusable PNG cache file."""
        if not is_valid_image_data(data):
            raise ValueError("Cannot cache invalid or incomplete artwork data.")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not is_valid_image_file(cache_path):
            with Image.open(io.BytesIO(data)) as source_image:
                source_image.load()
                converted = source_image.convert("RGBA")
                temporary = cache_path.with_suffix(".tmp.png")
                converted.save(temporary, format="PNG")
                temporary.replace(cache_path)
        return str(cache_path)

    def ask_sd_download_fallback_skip(self, system: str, art_name: str, error: Exception | str) -> str:
        """Prompt whether to try the next artwork provider or skip this image."""
        completed = threading.Event()
        answer = {"choice": "skip"}
        detail = str(error).strip() or "The provider returned invalid image data."
        if len(detail) > 360:
            detail = detail[:357] + "..."

        def show_dialog():
            dialog = None
            try:
                dialog = tk.Toplevel(self)
                dialog.title("Artwork Image Unavailable")
                dialog.configure(bg="#152235")
                dialog.transient(self)
                dialog.resizable(False, False)
                dialog.columnconfigure(0, weight=1)
                ttk.Label(
                    dialog,
                    text=f"Could not download usable artwork for {display_libretro_name(art_name)}\nSystem: {system}",
                    style="Section.TLabel",
                    wraplength=430,
                ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))
                ttk.Label(
                    dialog,
                    text=(
                        f"Error: {detail}\n\nTry the next artwork provider?\n"
                        "Fallback order: TheGamesDB → ScreenScraper → IGDB."
                    ),
                    style="Muted.TLabel",
                    wraplength=430,
                ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 16))
                auto_fallback_state = getattr(self, "_sd_auto_fallback_state", None)
                auto_fallback_var = tk.BooleanVar(
                    value=bool(auto_fallback_state and auto_fallback_state.get("enabled"))
                )
                ttk.Checkbutton(
                    dialog,
                    text="Automatically try fallback for the rest of this scan",
                    variable=auto_fallback_var,
                ).grid(row=2, column=0, sticky="w", padx=18, pady=(0, 12))
                buttons = ttk.Frame(dialog, style="Panel.TFrame")
                buttons.grid(row=3, column=0, sticky="e", padx=18, pady=(0, 18))

                def finish(choice: str):
                    answer["choice"] = choice
                    if auto_fallback_state is not None:
                        auto_fallback_state["enabled"] = bool(auto_fallback_var.get())
                    try:
                        if dialog is not None and dialog.winfo_exists():
                            dialog.grab_release()
                            dialog.destroy()
                    except tk.TclError:
                        pass
                    completed.set()

                dialog.protocol("WM_DELETE_WINDOW", lambda: finish("skip"))
                ttk.Button(buttons, text="Skip Image", command=lambda: finish("skip")).pack(
                    side="right", padx=(8, 0)
                )
                ttk.Button(
                    buttons,
                    text="Try Fallback",
                    style="Accent.TButton",
                    command=lambda: finish("fallback"),
                ).pack(side="right")
                dialog.grab_set()
                dialog.focus_force()
            except tk.TclError:
                try:
                    if dialog is not None and dialog.winfo_exists():
                        dialog.grab_release()
                        dialog.destroy()
                except tk.TclError:
                    pass
                answer["choice"] = "skip"
                completed.set()

        try:
            self.after(0, show_dialog)
        except tk.TclError:
            return "skip"
        completed.wait()
        return answer["choice"]

    def _scan_sd_worker(
        self,
        root: Path,
        source: str,
        size_names: list[str],
        include_gba: bool,
        progress_callback=None,
        use_hash_matching: bool = False,
        auto_fallback: bool = False,
    ) -> dict:
        # Shared with the main-thread fallback prompt so its checkbox can apply
        # automatically to every later download failure in this scan.
        self._sd_auto_fallback_state = {"enabled": bool(auto_fallback)}

        def report(heading, current=None, total=None, detail=""):
            if progress_callback:
                progress_callback(heading, current, total, detail)

        report("Scanning SD card folders", None, None, str(root))
        files = self.supported_files_on_sd(
            root,
            include_gba,
            progress_callback=lambda heading, current=None, total=None, detail="": report(
                heading, current, total, detail
            ),
        )
        folder = LIBRETRO_SOURCE_FOLDERS.get(source, "Named_Boxarts")
        existing_items: dict[tuple[str, str], tuple[int, CustomRomItem]] = {}
        existing_items_by_relative: dict[str, list[tuple[int, CustomRomItem]]] = {}
        for index, item in enumerate(self.custom_roms):
            relative = self.custom_art_relative_path(item)
            if relative:
                relative_key = relative.casefold()
                existing_items[(relative_key, item.size)] = (index, item)
                existing_items_by_relative.setdefault(relative_key, []).append((index, item))

        candidates: list[SdRomCandidate] = []
        unmatched: list[str] = []
        unmatched_games: list[dict[str, str]] = []
        seen_targets: set[str] = set()

        for number, (path, system) in enumerate(files, start=1):
            if number == 1 or number % 10 == 0 or number == len(files):
                report(
                    "Matching installed games against Libretro",
                    number,
                    max(1, len(files)),
                    f"{system}: {path.name}",
                )
            if number == 1 or number % 20 == 0:
                self.after(
                    0,
                    lambda current=number, total=len(files): self.status_var.set(
                        f"Matching installed games... {current}/{total}"
                    ),
                )
            try:
                target_name = validate_custom_art_name(path.stem)
            except ValueError:
                unmatched.append(f"Unsupported filename: {path.name}")
                continue
            try:
                relative = relative_path_from_root(root, path, system)
            except (OSError, ValueError):
                unmatched.append(f"Could not make a ROM-relative path: {path.name}")
                continue
            target_key = relative.casefold()
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            # Defer all provider matching until after existing thumbnails and
            # per-ROM cached source images have been checked. Candidate discovery
            # itself must not contact online artwork services.
            candidates.append(SdRomCandidate(path, system, target_name, relative, None))

        local_pack_matches: dict[str, ProviderResult] = {}
        # Test instances can be created without initializing Tk; reading vars()
        # avoids Tk's recursive __getattr__ when an optional setting is absent.
        app_state = vars(self)
        priority_setting = app_state.get("local_pack_priority_var")
        pack_setting = app_state.get("local_pack_var")
        local_search = getattr(self.providers, "search_local_pack_many", None)
        local_priority_enabled = bool(priority_setting is not None and priority_setting.get())
        if local_priority_enabled and pack_setting is not None and pack_setting.get().strip() and callable(local_search):
            for local_index, candidate in enumerate(candidates, start=1):
                if local_index == 1 or local_index % 20 == 0 or local_index == len(candidates):
                    report(
                        "Searching local pack before cached/provider artwork",
                        local_index,
                        max(1, len(candidates)),
                        f"{candidate.system}: {candidate.path.name}",
                    )
                try:
                    local_results = local_search(
                        strip_nointro_tags(candidate.title), max_results=1, system=candidate.system
                    )
                    if local_results and is_valid_image_data(local_results[0].image_data):
                        local_pack_matches[candidate.relative.casefold()] = local_results[0]
                except Exception:
                    # A local miss is not fatal; continue with the normal cache/provider chain.
                    continue

        # Resolve candidate directories once per size; thousands of ROMs should
        # not trigger thousands of repeated directory listings.
        output_roots_by_size = {
            size: self.sd_thumbnail_output_roots(root, size)
            for size in set(size_names)
        }

        # Decide which ROM/size pairs need work before attempting fallback search.
        # This avoids querying or downloading fallback art for complete existing
        # IMGS/IMGS2 output on subsequent scans.
        needed_sizes: dict[str, set[str]] = {}
        updates: dict[int, str] = {}
        skipped_existing = 0
        for index, candidate in enumerate(candidates, start=1):
            if index == 1 or index % 10 == 0 or index == len(candidates):
                report(
                    "Checking for existing thumbnails",
                    index,
                    max(1, len(candidates)),
                    candidate.path.name,
                )
            target_key = candidate.relative.casefold()
            if target_key in local_pack_matches:
                # Queue even already-complete sizes for refresh by the Custom Art build step.
                needed_sizes[target_key] = set(size_names)
                continue
            missing: set[str] = set()
            for size in size_names:
                key = (target_key, size)
                item_entry = existing_items.get(key)
                if item_entry:
                    item_index, item = item_entry
                    if item.image_path and is_valid_image_file(item.image_path):
                        skipped_existing += 1
                        continue
                output_path = self.existing_sd_thumbnail(
                    root, candidate.relative, size, output_roots_by_size[size]
                )
                if output_path is not None:
                    if item_entry:
                        updates[item_entry[0]] = str(output_path)
                    skipped_existing += 1
                    continue
                missing.add(size)
            if missing:
                needed_sizes[target_key] = missing

        matches: list[SdArtworkMatch] = []
        candidates_by_relative = {candidate.relative.casefold(): candidate for candidate in candidates}
        pre_cache_hits = 0
        for index, candidate in enumerate(candidates, start=1):
            if index == 1 or index % 5 == 0 or index == len(candidates):
                report(
                    "Checking cached artwork before providers",
                    index,
                    max(1, len(candidates)),
                    f"{candidate.system}: {candidate.path.name}",
                )
            target_key = candidate.relative.casefold()
            # Existing IMGS/IMGS2 and completed entries were checked above. If
            # nothing needs work for this ROM, do not even query Libretro's index.
            if not needed_sizes.get(target_key):
                continue
            local_result = local_pack_matches.get(target_key)
            if local_result is not None:
                matches.append(
                    SdArtworkMatch(
                        candidate.path,
                        candidate.system,
                        local_result.label,
                        candidate.relative,
                        "Local Pack",
                        local_result.image_data,
                    )
                )
                continue

            # First reuse a saved Custom Art source image associated with this ROM.
            # The custom-list image path can survive upgrades from older versions.
            cached_data = b""
            for _item_index, cached_item in existing_items_by_relative.get(target_key, []):
                cached_path = Path(cached_item.image_path) if cached_item.image_path else None
                if cached_path and is_valid_image_file(cached_path):
                    try:
                        candidate_data = cached_path.read_bytes()
                        if is_valid_image_data(candidate_data):
                            cached_data = candidate_data
                            break
                    except OSError:
                        pass

            # Next check the persistent cache keyed directly by ROM path. This
            # happens before find_libretro_art_name or any provider search.
            rom_cache_path = self.sd_scan_rom_cache_path(folder, candidate.system, candidate.relative)
            if not cached_data and is_valid_image_file(rom_cache_path):
                try:
                    candidate_data = rom_cache_path.read_bytes()
                    if is_valid_image_data(candidate_data):
                        cached_data = candidate_data
                    else:
                        rom_cache_path.unlink(missing_ok=True)
                except OSError:
                    cached_data = b""
            if cached_data:
                cache_tag = hashlib.sha256(target_key.encode("utf-8")).hexdigest()[:10]
                matches.append(
                    SdArtworkMatch(
                        candidate.path,
                        candidate.system,
                        f"{candidate.title} [rom-cache-{cache_tag}]",
                        candidate.relative,
                        "Cached",
                        cached_data,
                    )
                )
                pre_cache_hits += 1
                continue

            # Remove recognized No-Intro release/dump tags only from the online query.
            # The original title and relative ROM path remain unchanged for output/cache identity.
            query_title = strip_nointro_tags(candidate.title)

            # No usable local source image exists: only now ask the online providers.
            try:
                art_name = self.providers.find_libretro_art_name(query_title, candidate.system, folder)
            except Exception:
                art_name = None
            candidate.libretro_art_name = art_name
            if art_name:
                matches.append(
                    SdArtworkMatch(candidate.path, candidate.system, art_name, candidate.relative, "Libretro")
                )
                continue
            try:
                fallback_search = getattr(self.providers, "search_fallback_many", None)
                if callable(fallback_search):
                    fallback = fallback_search(
                        query_title,
                        max_results=1,
                        system=candidate.system,
                        after_provider="Libretro",
                    )
                else:
                    # Compatibility path for older embedders/test doubles.
                    tgdb_key_var = self.__dict__.get("tgdb_key_var")
                    if not (tgdb_key_var and tgdb_key_var.get().strip()):
                        raise LookupError("No Libretro match; add a TheGamesDB API key in Settings for fallback.")
                    fallback = self.providers.search_thegamesdb_many(
                        query_title, max_results=1, system=candidate.system
                    )
                if not fallback or not is_valid_image_data(fallback[0].image_data):
                    raise LookupError("No fallback provider returned usable image data")
                result = fallback[0]
                matches.append(
                    SdArtworkMatch(
                        candidate.path,
                        candidate.system,
                        result.label,
                        candidate.relative,
                        result.provider,
                        result.image_data,
                    )
                )
            except Exception as exc:
                # Opt-in hashing runs only after existing outputs, local image cache,
                # Libretro name matching, and the full online name fallback chain miss.
                if use_hash_matching:
                    report(
                        "Trying ROM hash matching",
                        index,
                        max(1, len(candidates)),
                        f"{candidate.system}: {candidate.path.name}",
                    )
                    try:
                        hash_results = self.providers.search_hash_fallback(
                            candidate.path, query_title, candidate.system
                        )
                        if not hash_results or not is_valid_image_data(hash_results[0].image_data):
                            raise LookupError("Hash providers returned no usable artwork")
                        hash_result = hash_results[0]
                        matches.append(
                            SdArtworkMatch(
                                candidate.path, candidate.system, hash_result.label,
                                candidate.relative, hash_result.provider, hash_result.image_data,
                            )
                        )
                        continue
                    except Exception as hash_error:
                        unmatched.append(
                            f"{candidate.system}: {candidate.path.name} "
                            f"(name search: {exc}; hash search: {hash_error})"
                        )
                        unmatched_games.append({
                            "title": candidate.path.name,
                            "system": candidate.system,
                            "path": str(candidate.path),
                            "relative": candidate.relative,
                        })
                else:
                    unmatched.append(f"{candidate.system}: {candidate.path.name} (provider fallback chain: {exc})")
                    unmatched_games.append({
                        "title": candidate.path.name,
                        "system": candidate.system,
                        "path": str(candidate.path),
                        "relative": candidate.relative,
                    })

        # Cache identity includes the provider, console and Libretro art folder.
        # The same title can therefore have separate images from each provider.
        match_key = lambda match: (match.provider, match.system, match.art_name)
        matches_by_art: dict[tuple[str, str, str], SdArtworkMatch] = {}
        needed_art: set[tuple[str, str, str]] = set()
        for match in matches:
            key = match_key(match)
            matches_by_art.setdefault(key, match)
            if needed_sizes.get(match.relative.casefold()):
                needed_art.add(key)

        downloaded: dict[tuple[str, str, str], bytes] = {}
        cache_paths: dict[tuple[str, str, str], Path] = {}
        download_errors: list[str] = []
        cache_hits = pre_cache_hits
        # Previous scraper versions cached source images as CustomRomItem paths.
        prior_item_cache_by_art: dict[tuple[str, str, str], Path] = {}
        for match in matches:
            key = match_key(match)
            if key not in needed_art:
                continue
            for _index, item in existing_items_by_relative.get(match.relative.casefold(), []):
                if item.image_path and is_valid_image_file(item.image_path):
                    prior_item_cache_by_art.setdefault(key, Path(item.image_path))
                    break

        for cache_index, key in enumerate(sorted(needed_art), start=1):
            if cache_index == 1 or cache_index % 5 == 0 or cache_index == len(needed_art):
                report(
                    "Checking cached artwork",
                    cache_index,
                    max(1, len(needed_art)),
                    f"{key[1]}: {display_libretro_name(key[2])}",
                )
            provider, system, art_name = key
            cache_source = folder if provider == "Libretro" else provider
            cache_path = self.sd_scan_cache_path(cache_source, system, art_name)
            cache_paths[key] = cache_path
            match = matches_by_art[key]
            if provider == "Local Pack" and match.image_data:
                # Always refresh scraper cache copies from a selected local-pack source.
                downloaded[key] = match.image_data
                try:
                    self.cache_sd_scan_image(cache_path, match.image_data, overwrite=True)
                    downloaded[key] = cache_path.read_bytes()
                except Exception as exc:
                    download_errors.append(
                        f"{system}: {display_libretro_name(art_name)} (local-pack cache refresh failed: {exc})"
                    )
                continue
            if provider == "Cached" and match.image_data:
                # The per-ROM cache was already checked before any provider query.
                # Populate the general source cache for compatibility with older
                # paths, while counting only the original per-ROM hit above.
                try:
                    self.cache_sd_scan_image(cache_path, match.image_data)
                    downloaded[key] = cache_path.read_bytes()
                except Exception as exc:
                    download_errors.append(
                        f"{system}: {display_libretro_name(art_name)} (cache write failed: {exc})"
                    )
                continue
            if is_valid_image_file(cache_path):
                try:
                    cached_data = cache_path.read_bytes()
                except OSError:
                    cached_data = b""
                if is_valid_image_data(cached_data):
                    downloaded[key] = cached_data
                    cache_hits += 1
                    continue
                try:
                    cache_path.unlink()
                except OSError:
                    pass

            # Migrate/reuse a prior source-image cache if one is associated with
            # this ROM entry. This also avoids re-downloading when only size changes.
            legacy_path = prior_item_cache_by_art.get(key)
            if legacy_path and is_valid_image_file(legacy_path):
                try:
                    legacy_data = legacy_path.read_bytes()
                    if is_valid_image_data(legacy_data):
                        self.cache_sd_scan_image(cache_path, legacy_data)
                        downloaded[key] = cache_path.read_bytes()
                        cache_hits += 1
                        continue
                except (OSError, ValueError, SyntaxError):
                    pass
            if cache_path.exists() and not is_valid_image_file(cache_path):
                try:
                    cache_path.unlink()
                except OSError:
                    pass

            # Fallback searches already downloaded and validated their selected
            # image. Persist those bytes directly; don't fetch the URL again.
            match = matches_by_art[key]
            if match.provider != "Libretro" and match.image_data:
                data = match.image_data
                downloaded[key] = data
                try:
                    self.cache_sd_scan_image(cache_path, data)
                    downloaded[key] = cache_path.read_bytes()
                except Exception as exc:
                    download_errors.append(
                        f"{system}: {display_libretro_name(art_name)} (cache write failed: {exc})"
                    )

        to_download = needed_art - set(downloaded)
        # Only Libretro matches need a separate raw-image fetch. Fallback results
        # carry their validated image bytes already.
        to_download = {key for key in to_download if key[0] == "Libretro"}
        if to_download:
            report(
                "Downloading uncached artwork",
                0,
                len(to_download),
                f"{len(to_download):,} images to download",
            )
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_art = {
                    executor.submit(http_get, libretro_raw_url(system, folder, art_name)): key
                    for key in sorted(to_download)
                    for _provider, system, art_name in [key]
                }
                for download_index, future in enumerate(as_completed(future_to_art), start=1):
                    key = future_to_art[future]
                    _provider, system, art_name = key
                    url = libretro_raw_url(system, folder, art_name)
                    report(
                        "Downloading uncached artwork",
                        download_index,
                        len(future_to_art),
                        f"{system}: {display_libretro_name(art_name)}",
                    )
                    try:
                        data = future.result()
                        if not is_valid_image_data(data):
                            raise ValueError("Provider returned invalid or incomplete image data")
                    except Exception as exc:
                        auto_fallback_state = getattr(self, "_sd_auto_fallback_state", {})
                        if auto_fallback_state.get("enabled"):
                            action = "fallback"
                        else:
                            action = self.ask_sd_download_fallback_skip(system, art_name, exc)
                        if action == "fallback":
                            candidate = candidates_by_relative.get(matches_by_art[key].relative.casefold())
                            query = candidate.title if candidate else Path(art_name).stem
                            try:
                                try:
                                    fallback = self.providers.search_fallback_many(
                                        strip_nointro_tags(query),
                                        max_results=1,
                                        system=system,
                                        after_provider="Libretro",
                                        prior_errors=[f"Libretro image download: {exc}"],
                                    )
                                except Exception as name_fallback_error:
                                    if not use_hash_matching or candidate is None:
                                        raise
                                    report(
                                        "Trying ROM hash matching",
                                        download_index,
                                        len(future_to_art),
                                        f"{system}: {candidate.path.name}",
                                    )
                                    fallback = self.providers.search_hash_fallback(
                                        candidate.path, strip_nointro_tags(query), system
                                    )
                                if not fallback or not is_valid_image_data(fallback[0].image_data):
                                    raise LookupError("No fallback provider returned usable image data")
                                data = fallback[0].image_data
                                downloaded[key] = data
                                cache_path = cache_paths[key]
                                self.cache_sd_scan_image(cache_path, data)
                                downloaded[key] = cache_path.read_bytes()
                                report(
                                    f"Artwork recovered from {fallback[0].provider}",
                                    download_index,
                                    len(future_to_art),
                                    f"{system}: {query}",
                                )
                            except Exception as fallback_error:
                                download_errors.append(
                                    f"{system}: {display_libretro_name(art_name)} (fallback failed: {fallback_error})"
                                )
                                continue
                        else:
                            download_errors.append(
                                f"{system}: {display_libretro_name(art_name)} (skipped after download error: {exc})"
                            )
                            continue
                    else:
                        downloaded[key] = data
                        try:
                            cache_path = cache_paths[key]
                            self.cache_sd_scan_image(cache_path, data)
                            downloaded[key] = cache_path.read_bytes()
                        except Exception as exc:
                            download_errors.append(
                                f"{system}: {display_libretro_name(art_name)} (cache write failed: {exc})"
                            )

        additions: list[CustomRomItem] = []
        matched_files = len(matches)
        for match_index, match in enumerate(matches, start=1):
            if match_index == 1 or match_index % 10 == 0 or match_index == len(matches):
                report(
                    "Preparing Custom Art entries",
                    match_index,
                    max(1, len(matches)),
                    f"{match.system}: {match.path.name}",
                )
            relative_key = match.relative.casefold()
            if not needed_sizes.get(relative_key):
                continue
            key_art = match_key(match)
            data = downloaded.get(key_art)
            if not data:
                continue
            # Persist the selected source image by ROM identity, independent of
            # provider name/label. The next scan checks this before online lookup.
            rom_cache_path = self.sd_scan_rom_cache_path(folder, match.system, match.relative)
            try:
                self.cache_sd_scan_image(
                    rom_cache_path,
                    data,
                    overwrite=(local_priority_enabled and match.provider == "Local Pack"),
                )
            except Exception as exc:
                download_errors.append(
                    f"{match.system}: {match.path.name} (per-ROM cache write failed: {exc})"
                )
            cache_source = folder if match.provider == "Libretro" else match.provider
            provider_cache_path = cache_paths.get(key_art) or self.sd_scan_cache_path(
                cache_source, match.system, match.art_name
            )
            # Custom entries point at the per-ROM cache so subsequent scans can
            # reuse the exact image before querying providers, even if providers
            # later rename or remove their search result.
            image_path = str(rom_cache_path if is_valid_image_file(rom_cache_path) else provider_cache_path)
            # Cache paths are persistent and deterministic. If writing there
            # failed, make a best effort to keep a temporary source image cache.
            if not is_valid_image_file(image_path):
                try:
                    image_path = self.cache_provider_result(
                        ProviderResult(match.provider, match.art_name, data, match.system), cache_source
                    )
                except Exception:
                    continue
            for size in needed_sizes[relative_key]:
                key = (relative_key, size)
                existing_item = existing_items.get(key)
                if existing_item:
                    updates[existing_item[0]] = image_path
                    continue
                additions.append(
                    CustomRomItem(
                        str(match.path),
                        match.path.stem,
                        "----",
                        match.path.stem,
                        image_path=image_path,
                        size=size,
                        system=match.system,
                        rom_relative_path=match.relative,
                    )
                )

        return {
            "files": len(files),
            "matched_files": matched_files,
            "additions": additions,
            "updates": updates,
            "unmatched": unmatched,
            "unmatched_games": unmatched_games,
            "download_errors": download_errors,
            "skipped_existing": skipped_existing,
            "cache_hits": cache_hits,
        }

    def finish_sd_scan(self, result: dict):
        self.close_operation_progress("sd_scan_progress_window")
        additions = result["additions"]
        for index, image_path in result.get("updates", {}).items():
            if 0 <= index < len(self.custom_roms):
                self.custom_roms[index].image_path = image_path
        self.custom_roms.extend(additions)
        self.refresh_custom_roms(
            list(range(len(self.custom_roms) - len(additions), len(self.custom_roms))) if additions else []
        )
        self.save_settings()
        self.scan_running = False
        self.scan_sd_button.configure(state="normal")
        self.status_var.set(f"SD scan complete. Added {len(additions)} custom artwork entries.")
        self.show_sd_scan_results(result)

    def fail_sd_scan(self, error: Exception):
        self.close_operation_progress("sd_scan_progress_window")
        self.scan_running = False
        self.scan_sd_button.configure(state="normal")
        self.status_var.set("SD scan failed.")
        messagebox.showwarning(APP_NAME, str(error))

    def show_sd_scan_results(self, result: dict):
        unmatched_games = result.get("unmatched_games", [])
        if len(unmatched_games) > 50:
            add_to_queue = messagebox.askyesno(
                APP_NAME,
                f"{len(unmatched_games):,} games had no artwork match. Add them to the manual search list?",
                detail="A large list can be difficult to review. You can still use the saved scan report if you skip the list.",
                parent=self,
            )
            self.sd_scan_unmatched_games = unmatched_games if add_to_queue else []
        else:
            self.sd_scan_unmatched_games = unmatched_games
        options = [
            f"{Path(game['path']).name} — {game['system']}"
            for game in self.sd_scan_unmatched_games
        ]
        self.sd_scan_game_combo.configure(values=options)
        self.clear_sd_scan_games_button.configure(state="normal" if options else "disabled")
        self.sd_scan_game_var.set("")
        self.active_sd_scan_game = None
        report_lines = [
            f"No artwork match found for {game['title']} on any of the media providers."
            for game in unmatched_games
        ]
        report_dir = self.base_dir / OUTPUT_FOLDER_NAME / "SD Scan Reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"sd_scan_{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        counter = 2
        while report_path.exists():
            report_path = report_dir / f"sd_scan_{time.strftime('%Y-%m-%d_%H-%M-%S')}_{counter}.txt"
            counter += 1
        report_text = "\n".join(report_lines) if report_lines else "Artwork matches were found for all scanned games."
        report_path.write_text(report_text + "\n", encoding="utf-8")
        report_path.with_suffix(".json").write_text(
            json.dumps({"unmatched_games": unmatched_games}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        dialog = tk.Toplevel(self)
        dialog.title("SD Scan Results")
        dialog.configure(bg="#152235")
        dialog.transient(self)
        dialog.geometry("620x360")
        dialog.minsize(520, 280)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)
        ttk.Label(dialog, text="SD library scan complete", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 6)
        )
        summary = (
            f"Found {result['files']} supported files, matched {result['matched_files']}, "
            f"and added {len(result['additions'])} artwork entries."
        )
        ttk.Label(dialog, text=summary, style="Muted.TLabel", wraplength=570).grid(
            row=1, column=0, sticky="w", padx=18, pady=(0, 10)
        )
        text_box = tk.Text(
            dialog,
            bg="#101a29",
            fg="#edf4fb",
            insertbackground="#edf4fb",
            relief="flat",
            wrap="word",
            font=("Segoe UI", 9),
        )
        text_box.grid(row=2, column=0, sticky="nsew", padx=(18, 0), pady=(0, 12))
        text_scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=text_box.yview)
        text_scrollbar.grid(row=2, column=1, sticky="ns", padx=(0, 18), pady=(0, 12))
        text_box.configure(yscrollcommand=text_scrollbar.set)
        text_box.insert("1.0", report_text)
        text_box.configure(state="disabled")
        ttk.Label(dialog, text=f"Saved report: {report_path}", style="Muted.TLabel", wraplength=570).grid(
            row=3, column=0, sticky="w", padx=18, pady=(0, 10)
        )
        ttk.Button(dialog, text="Done", style="Accent.TButton", command=dialog.destroy).grid(
            row=4, column=0, sticky="e", padx=18, pady=(0, 18)
        )

    def next_custom_code(self) -> str:
        used = {item.new_code for item in self.custom_roms}
        for prefix in ("Z", "X", "Q"):
            for number in range(1, 1000):
                code = f"{prefix}{number:03d}"
                if code not in used and code not in self.known_game_codes:
                    return code
        raise ValueError("Too many homebrew ROMs to auto-assign codes.")

    def add_custom_roms(self):
        paths = filedialog.askopenfilenames(filetypes=[("All files", "*.*")])
        if not paths:
            return
        added = 0
        selected_size = self.size_var.get()
        existing_paths = {(item.rom_path, item.size) for item in self.custom_roms if item.rom_path}
        existing_names = set()
        for item in self.custom_roms:
            relative = self.custom_art_relative_path(item)
            identity = ("path:" + relative.casefold()) if relative else ("custom:" + item.new_code.casefold())
            existing_names.add((identity, item.size))
        for raw_path in paths:
            path = Path(raw_path)
            if (str(path), selected_size) in existing_paths:
                continue
            try:
                title, code = read_gba_header(path)
            except Exception:
                title, code = path.stem, "----"
            try:
                thumb_name = validate_custom_art_name(path.stem)
            except ValueError as exc:
                messagebox.showwarning(APP_NAME, f"{path.name}: {exc}")
                continue
            system = system_for_path(path) or ""
            relative = infer_relative_rom_path(path, system) if system else ""
            identity = ("path:" + relative.casefold()) if relative else ("custom:" + thumb_name.casefold())
            if (identity, selected_size) in existing_names:
                continue
            self.custom_roms.append(
                CustomRomItem(
                    str(path),
                    title or path.stem,
                    code or "----",
                    thumb_name,
                    size=selected_size,
                    system=system,
                    rom_relative_path=relative,
                )
            )
            existing_paths.add((str(path), selected_size))
            existing_names.add((identity, selected_size))
            added += 1
        if added:
            self.refresh_custom_roms()
            self.status_var.set(f"Added {added} custom art names.")

    def add_custom_name(self):
        dialog = tk.Toplevel(self)
        dialog.title("Add Custom Art Name")
        dialog.configure(bg="#152235")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        ttk.Label(dialog, text="ROM filename (without extension) or system folder").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))
        name_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=name_var, width=42)
        entry.grid(row=1, column=0, sticky="ew", padx=16)
        ttk.Label(dialog, text="For example: Pokemon Emerald Rogue or Game Boy Advance", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=16, pady=(6, 12))
        buttons = ttk.Frame(dialog, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="e", padx=16, pady=(0, 16))

        def add():
            try:
                name = validate_custom_art_name(name_var.get())
            except ValueError as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=dialog)
                return
            selected_size = self.size_var.get()
            if (name.casefold(), selected_size) in {
                (item.new_code.casefold(), item.size)
                for item in self.custom_roms
                if not self.custom_art_relative_path(item)
            }:
                messagebox.showinfo(APP_NAME, "That name and size are already in the list.", parent=dialog)
                return
            self.custom_roms.append(CustomRomItem("", name, "----", name, size=selected_size))
            self.refresh_custom_roms([len(self.custom_roms) - 1])
            self.status_var.set(f"Added {name}.")
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Add", style="Accent.TButton", command=add).pack(side="right")
        entry.bind("<Return>", lambda _event: add())
        entry.focus_set()

    def selected_custom_indices(self) -> list[int]:
        if not hasattr(self, "custom_tree"):
            return []
        indices = []
        for item_id in self.custom_tree.selection():
            try:
                indices.append(int(item_id))
            except ValueError:
                pass
        return indices

    def on_custom_tree_click(self, event):
        if self.custom_tree.identify_region(event.x, event.y) in ("heading", "separator"):
            return
        if self.custom_tree.identify_row(event.y):
            return
        self.custom_tree.selection_remove(self.custom_tree.selection())
        self.custom_tree.focus("")
        self.set_custom_crop_controls(CropSettings())
        self.after_idle(self.update_custom_preview)

    def on_custom_selection_changed(self):
        indices = self.selected_custom_indices()
        if len(indices) == 1:
            item = self.custom_roms[indices[0]]
            self.size_var.set(item.size)
            self.set_custom_crop_controls(self.crop_from_dict(item.crop))
        elif not indices:
            self.set_custom_crop_controls(CropSettings())
        self.update_custom_preview()

    def on_custom_crop_changed(self):
        if self.loading_custom_crop:
            return
        indices = self.selected_custom_indices()
        crop = asdict(self.custom_crop())
        for index in indices:
            self.custom_roms[index].crop = crop.copy()
        self.update_custom_preview()

    def refresh_custom_roms(self, preserve_selection: list[int] | None = None):
        if preserve_selection is None:
            preserve_selection = self.selected_custom_indices()
        self.custom_tree.delete(*self.custom_tree.get_children())
        for index, item in enumerate(self.custom_roms):
            image_name = Path(item.image_path).name if item.image_path else ""
            source = item.system or ("Manual" if not item.rom_path else "Other")
            self.custom_tree.insert("", "end", iid=str(index), values=(item.new_code, source, item.size, image_name))
        valid_selection = [str(index) for index in preserve_selection if 0 <= index < len(self.custom_roms)]
        if valid_selection:
            self.custom_tree.selection_set(valid_selection)
            self.custom_tree.focus(valid_selection[0])
            self.custom_tree.see(valid_selection[0])
        if hasattr(self, "custom_scroll_sync"):
            self.custom_scroll_sync()
        self.on_custom_selection_changed()

    def apply_custom_size_to_selection(self):
        indices = self.selected_custom_indices()
        new_size = self.size_var.get()
        seen = set()
        for index, item in enumerate(self.custom_roms):
            size = new_size if index in indices else item.size
            key = (item.new_code.casefold(), size)
            if key in seen:
                messagebox.showwarning(APP_NAME, "That change would create a duplicate custom name and size.")
                return
            seen.add(key)
        for index in indices:
            self.custom_roms[index].size = new_size
            self.custom_roms[index].crop = None
        self.set_custom_crop_controls(CropSettings())
        if indices:
            self.refresh_custom_roms(indices)
        else:
            self.update_custom_preview()

    def reset_custom_crop(self):
        self.set_custom_crop_controls(CropSettings())

    def set_custom_image(self):
        indices = self.selected_custom_indices()
        if not indices:
            messagebox.showinfo(APP_NAME, "Select one or more entries first.")
            return
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")])
        if not path:
            return
        for index in indices:
            self.custom_roms[index].image_path = path
            self.custom_roms[index].crop = None
        self.set_custom_crop_controls(CropSettings())
        self.refresh_custom_roms(indices)

    def remove_custom_roms(self):
        indices = set(self.selected_custom_indices())
        if not indices:
            return
        self.custom_roms = [item for index, item in enumerate(self.custom_roms) if index not in indices]
        next_index = min(indices) if self.custom_roms else -1
        self.refresh_custom_roms([min(next_index, len(self.custom_roms) - 1)] if next_index >= 0 else [])

    def on_custom_output_layout_changed(self):
        self.update_custom_preview()
        self.save_settings()

    def apply_custom_code(self):
        indices = self.selected_custom_indices()
        if len(indices) != 1:
            messagebox.showinfo(APP_NAME, "Select one entry to edit its name.")
            return
        try:
            code = validate_custom_art_name(self.custom_code_var.get())
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return
        item = self.custom_roms[indices[0]]
        if self.custom_output_layout_var.get() == "Mirror ROM folders" and self.custom_art_relative_path(item):
            messagebox.showinfo(
                APP_NAME,
                "Mirrored artwork always uses the ROM's actual filename and relative folder. "
                "Rename the ROM and scan again to change its path. The custom name applies to Legacy CUSTOM artwork.",
            )
            return
        size = item.size
        used = {
            (other.new_code.casefold(), other.size)
            for index, other in enumerate(self.custom_roms)
            if index != indices[0]
            and (
                self.custom_output_layout_var.get() == "Legacy CUSTOM"
                or not self.custom_art_relative_path(other)
            )
        }
        if (code.casefold(), size) in used:
            messagebox.showwarning(APP_NAME, "That name and size is already used by another custom entry.")
            return
        self.custom_roms[indices[0]].new_code = code
        self.refresh_custom_roms(indices)

    def update_custom_preview(self):
        indices = self.selected_custom_indices()
        if not indices:
            if hasattr(self, "custom_preview_info"):
                self.custom_preview_label.configure(image="", width=300, height=210)
                self.custom_preview_photo = None
                self.custom_preview_info.configure(text="Select an entry to preview its image.")
            return
        item = self.custom_roms[indices[0]]
        self.custom_code_var.set(item.new_code)
        crop = self.crop_from_dict(item.crop)
        if not item.image_path:
            self.custom_preview_label.configure(image="", width=300, height=210)
            self.custom_preview_photo = None
            self.custom_preview_info.configure(text=f"{item.new_code}.bmp — no image set")
            return
        try:
            image = Image.open(item.image_path)
            w, h, _folder = self.size_details(item.size)
            thumb = crop_image(image, (w, h), crop)
            preview = thumb.resize((w * 3, h * 3), Image.Resampling.NEAREST)
            self.custom_preview_photo = ImageTk.PhotoImage(preview)
            self.custom_preview_label.configure(image=self.custom_preview_photo, width=w * 3, height=h * 3)
            folder_name = self.size_details(item.size)[2]
            layout = self.custom_output_layout_var.get()
            relative = self.custom_art_relative_path(item)
            if layout == "Mirror ROM folders" and relative:
                mirrored = mirrored_thumbnail_path(Path(folder_name), relative)
                self.custom_preview_info.configure(text=f"{mirrored.as_posix()} ({item.size})")
            else:
                self.custom_preview_info.configure(text=f"{folder_name}/CUSTOM/{item.new_code}.bmp ({item.size})")
        except (OSError, ValueError) as exc:
            self.custom_preview_info.configure(text=f"Could not preview image: {exc}")

    def build_custom_rom_output(self):
        if self.custom_build_running:
            return
        if not self.custom_roms:
            messagebox.showinfo(APP_NAME, "Add artwork entries first.")
            return
        missing = [item.new_code for item in self.custom_roms if not item.image_path]
        if missing:
            messagebox.showwarning(APP_NAME, "Set an image for each entry before building the art pack.")
            return

        layout = self.custom_output_layout_var.get()
        mirror_entries: dict[int, str] = {}
        custom_entries: dict[str, set[str]] = {"80x80": set(), "120x80": set()}
        destinations: dict[tuple[str, str], str] = {}
        tasks = []
        try:
            # Validate all destinations before doing any disk writes. This catches
            # collisions in legacy CUSTOM mode before the progress window opens.
            for index, item in enumerate(self.custom_roms):
                relative = self.custom_art_relative_path(item) if layout == "Mirror ROM folders" else ""
                if relative:
                    mirror_entries[index] = relative
                elif not self.is_extension_default_name(item.new_code):
                    custom_entries[item.size].add(item.new_code.casefold())

            over_limit = [size for size, names in custom_entries.items() if len(names) > 256]
            if over_limit:
                labels = ", ".join(over_limit)
                messagebox.showwarning(
                    APP_NAME,
                    f"Legacy CUSTOM exceeds its 256-image limit for: {labels}.\n\n"
                    "Use Mirror ROM folders for ROM-matched artwork, or reduce name-only artwork to 256 images per size. "
                    "System defaults such as gb.bmp and nes.bmp do not count toward the limit.",
                )
                return

            for index, item in enumerate(self.custom_roms):
                _w, _h, folder_name = self.size_details(item.size)
                if index in mirror_entries:
                    relative_target = mirrored_thumbnail_path(Path(folder_name), mirror_entries[index])
                else:
                    relative_target = output_path_for_custom_name(Path(folder_name), item.new_code)
                identity = (item.size, str(relative_target).casefold())
                if identity in destinations:
                    messagebox.showwarning(
                        APP_NAME,
                        "Two entries would write to the same artwork filename:\n\n"
                        f"{destinations[identity]}\n{item.new_code}\n\n"
                        "Use mirrored folders or remove/rename the duplicate entry before building.",
                    )
                    return
                destinations[identity] = item.new_code
                w, h, _folder = self.size_details(item.size)
                tasks.append(
                    {
                        "image_path": str(item.image_path),
                        "name": validate_custom_art_name(item.new_code),
                        "size": item.size,
                        "width": w,
                        "height": h,
                        "target_relative": relative_target.as_posix(),
                        "crop": asdict(self.crop_from_dict(item.crop)),
                        "mirrored": index in mirror_entries,
                    }
                )
        except Exception as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return

        self.custom_build_running = True
        self.build_custom_art_button.configure(state="disabled")
        self.custom_art_progress_window = OperationProgressWindow(
            self,
            "Build Art Pack",
            f"Preparing to build {len(tasks):,} thumbnail(s)...",
        )

        def worker():
            run_dir = None
            made_mirrored = 0
            made_custom = 0
            try:
                run_dir = self.output_run_dir()
                total = len(tasks)
                for index, task in enumerate(tasks, start=1):
                    self.queue_operation_progress(
                        "custom_art_progress_window",
                        f"Building thumbnail {index:,} of {total:,}",
                        index - 1,
                        total,
                        f"{task['name']}  →  {task['target_relative']}",
                    )
                    with Image.open(task["image_path"]) as source_image:
                        thumb = crop_image(
                            source_image,
                            (task["width"], task["height"]),
                            CropSettings(**task["crop"]),
                        )
                        target = run_dir / Path(task["target_relative"])
                        write_ezflash_bmp(thumb, target)
                    if task["mirrored"]:
                        made_mirrored += 1
                    else:
                        made_custom += 1
                    self.queue_operation_progress(
                        "custom_art_progress_window",
                        f"Building thumbnail {index:,} of {total:,}",
                        index,
                        total,
                        f"Created {task['name']}  →  {task['target_relative']}",
                    )
                self.after(
                    0,
                    lambda result_dir=run_dir, mirrored=made_mirrored, custom=made_custom: self.finish_custom_art_output(
                        result_dir, mirrored, custom, layout, None
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda error=exc, result_dir=run_dir, mirrored=made_mirrored, custom=made_custom: self.finish_custom_art_output(
                        result_dir, mirrored, custom, layout, error
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def finish_custom_art_output(
        self,
        run_dir: Path | None,
        made_mirrored: int,
        made_custom: int,
        layout: str,
        error: Exception | None,
    ):
        self.close_operation_progress("custom_art_progress_window")
        self.custom_build_running = False
        if hasattr(self, "build_custom_art_button"):
            self.build_custom_art_button.configure(state="normal")
        if error is not None:
            self.status_var.set("Art pack build failed.")
            partial = f"\n\nPartial output may be available at:\n{run_dir}" if run_dir else ""
            messagebox.showwarning(APP_NAME, f"Could not build the art pack:\n{error}{partial}")
            return
        self.status_var.set(f"Art pack created: {run_dir}")
        extra = (
            f"\nMirrored files: {made_mirrored}; CUSTOM files: {made_custom}."
            if layout == "Mirror ROM folders"
            else "\nOutput layout: legacy CUSTOM."
        )
        messagebox.showinfo(APP_NAME, f"Art pack created:\n{run_dir}{extra}")

    def update_preview(self):
        if not self.current_source_image:
            return
        w, h, _folder = self.selected_size()
        thumb = crop_image(self.current_source_image, (w, h), self.current_crop())
        preview = thumb.resize((w * 3, h * 3), Image.Resampling.NEAREST)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.preview_photo, width=w * 3, height=h * 3)
        label = self.current_result.label if self.current_result else ""
        system = self.current_result.system if self.current_result else self.preview_system_var.get()
        self.preview_info.configure(text=f"{system} - {self.preview_provider_var.get()} - {label} - {w}x{h}")
        self.status_var.set("Preview ready.")

    def update_build_preview(self):
        if not self.build_source_image or not hasattr(self, "build_preview_label"):
            return
        w, h, _folder = self.selected_size()
        thumb = crop_image(self.build_source_image, (w, h), self.build_crop())
        preview = thumb.resize((w * 3, h * 3), Image.Resampling.NEAREST)
        self.build_preview_photo = ImageTk.PhotoImage(preview)
        self.build_preview_label.configure(image=self.build_preview_photo, width=w * 3, height=h * 3)
        label = self.build_result.label if self.build_result else ""
        self.build_preview_info.configure(text=f"{self.build_provider_var.get()} - {label} - {w}x{h}")
        self.status_var.set("Build preview ready.")

    def add_exception(self):
        if self.preview_system_var.get() != DEFAULT_SYSTEM:
            messagebox.showinfo(APP_NAME, "Exceptions only apply to Game Boy Advance artwork.")
            return
        if not self.current_result:
            messagebox.showinfo(APP_NAME, "Search for artwork or choose an image first.")
            return
        title = self.search_var.get().strip()
        rule = ExceptionRule(
            title=title,
            code="",
            size=self.size_var.get(),
            provider=self.current_result.provider,
            label=self.current_result.label,
            source=self.preview_libretro_source_var.get() if self.current_result.provider == "Libretro" else "",
            local_path=self.current_local_path if self.current_result.provider == "Local Image" else "",
            crop=asdict(self.current_crop()),
        )
        self.exceptions = [
            item
            for item in self.exceptions
            if not (clean_title(item.title).lower() == clean_title(title).lower() and item.size == self.size_var.get())
        ]
        self.exceptions.append(rule)
        self.refresh_exceptions()
        self.save_settings()

    def remove_exception(self):
        selected = self.exception_tree.selection()
        if not selected:
            return
        selected_keys = {
            f"{self.exception_tree.item(item, 'values')[0]}|{self.exception_tree.item(item, 'values')[1]}"
            for item in selected
        }
        self.exceptions = [item for item in self.exceptions if f"{item.title}|{item.size}" not in selected_keys]
        self.refresh_exceptions()
        self.save_settings()

    def refresh_exceptions(self):
        self.exception_tree.delete(*self.exception_tree.get_children())
        for rule in self.exceptions:
            self.exception_tree.insert("", "end", values=(rule.title, rule.size, rule.provider, rule.label))
        if hasattr(self, "exception_scroll_sync"):
            self.exception_scroll_sync()

    def choose_local_pack(self):
        path = filedialog.askdirectory()
        if path:
            self.local_pack_var.set(path)
            self.providers.local_art_index = None
            self.providers.local_art_index_root = None
            self.providers.local_art_files = []
            self.providers.local_art_indexes_by_system = {}
            self.providers.local_art_token_indexes_by_system = {}
            self.update_local_pack_label()
            self.save_settings()
            self.on_source_change()

    def exception_for(self, title: str, size: str) -> ExceptionRule | None:
        key = clean_title(title).lower()
        for rule in self.exceptions:
            if clean_title(rule.title).lower() == key and rule.size == size:
                return rule
        return None

    def exception_rules_for(self, title: str) -> list[ExceptionRule]:
        key = clean_title(title).lower()
        return [rule for rule in self.exceptions if clean_title(rule.title).lower() == key]

    def output_run_dir(self) -> Path:
        root = self.base_dir / OUTPUT_FOLDER_NAME
        root.mkdir(exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        run = root / stamp
        counter = 2
        while run.exists():
            run = root / f"{stamp}_{counter}"
            counter += 1
        run.mkdir()
        return run

    def build_pack(self):
        if self.running:
            return
        self.running = True
        self.cancel_build_requested = False
        if hasattr(self, "build_button"):
            self.build_button.configure(state="disabled")
        if hasattr(self, "cancel_build_button"):
            self.cancel_build_button.pack(anchor="w", pady=(8, 0), after=self.build_button)
        self.set_build_progress(0, "Preparing thumbnail pack...", "")
        threading.Thread(target=self._build_pack_worker, daemon=True).start()

    def cancel_build(self):
        if not self.running:
            return
        self.cancel_build_requested = True
        if hasattr(self, "cancel_build_button"):
            self.cancel_build_button.configure(state="disabled")
        self.set_build_progress(text="Cancelling after the current thumbnail...")

    def _build_pack_worker(self):
        try:
            selected_size_name = self.size_var.get()
            run_dir = self.output_run_dir()
            cache = self.base_dir / CACHE_FOLDER_NAME / "libretro_nointro_gba_library.json"
            library = load_gba_library(cache)
            exception_title_keys = {
                clean_title(rule.title).lower()
                for rule in self.exceptions
            }
            if self.exceptions_only_var.get():
                library = [
                    entry
                    for entry in library
                    if clean_title(entry.title).lower() in exception_title_keys
                ]
            allowed = self.selected_rom_regions()
            if not allowed and not exception_title_keys:
                self.set_build_progress(0, "Choose at least one ROM/output region before building.", "")
                return
            tasks = []
            for entry in library:
                rules = self.exception_rules_for(entry.title)
                region_included = bool(title_regions(entry.title) & allowed)
                if not region_included and not rules:
                    continue
                if self.exceptions_only_var.get():
                    for rule in rules:
                        tasks.append((entry, rule.size, rule))
                elif not region_included:
                    for rule in rules:
                        tasks.append((entry, rule.size, rule))
                else:
                    tasks.append((entry, selected_size_name, self.exception_for(entry.title, selected_size_name)))
                    for rule in rules:
                        if rule.size != selected_size_name:
                            tasks.append((entry, rule.size, rule))
            total = len(tasks)
            if total == 0:
                self.set_build_progress(0, "No matching games found for this build.", "")
                return
            made = missed = failed = 0
            prefetched_images = {}
            prefetched_errors = {}
            task_art_names = {}
            build_state = vars(self)
            local_priority_var = build_state.get("local_pack_priority_var")
            local_pack_var = build_state.get("local_pack_var")
            local_priority_for_build = bool(
                local_priority_var is not None
                and local_priority_var.get()
                and local_pack_var is not None
                and local_pack_var.get().strip()
            )
            if local_priority_for_build:
                for task_number, (entry, _size_name, rule) in enumerate(tasks, start=1):
                    if rule:
                        continue  # Preserve explicit per-title exceptions.
                    try:
                        local_result = self.providers.search_local_pack_many(
                            entry.title, max_results=1, system=DEFAULT_SYSTEM
                        )[0]
                        if is_valid_image_data(local_result.image_data):
                            prefetched_images[task_number] = local_result.image_data
                    except Exception:
                        pass
            normal_libretro_build = self.build_provider_var.get() == "Libretro"
            if normal_libretro_build:
                unique_art_urls = {}
                self.set_build_progress(0, "Matching artwork to games...", "")
                art_by_code_root = self.providers.direct_libretro_art_map(self.build_libretro_source_var.get())
                for task_number, (entry, _size_name, rule) in enumerate(tasks, start=1):
                    if rule or task_number in prefetched_images:
                        continue
                    art_match = art_by_code_root.get(entry.code[:3] if entry.code else "")
                    if art_match:
                        folder, art_name = art_match
                        task_art_names[task_number] = (folder, art_name)
                        unique_art_urls.setdefault(
                            (folder, art_name),
                            libretro_raw_url(DEFAULT_SYSTEM, folder, art_name),
                        )

                if unique_art_urls:
                    self.set_build_progress(0, f"Downloading {len(unique_art_urls)} artwork files...", "")
                    downloaded_art = {}
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        future_to_art = {
                            executor.submit(http_get, url): art_key
                            for art_key, url in unique_art_urls.items()
                        }
                        for done_count, future in enumerate(as_completed(future_to_art), start=1):
                            art_key = future_to_art[future]
                            if self.cancel_build_requested:
                                for pending in future_to_art:
                                    pending.cancel()
                                summary = "Cancelled while downloading artwork."
                                self.set_build_progress((done_count - 1) / len(future_to_art) * 45, summary, f"Partial output saved to:\n{run_dir}")
                                return
                            try:
                                image_data = future.result()
                                if not is_valid_image_data(image_data):
                                    raise ValueError("Libretro returned invalid or incomplete image data")
                                downloaded_art[art_key] = image_data
                            except Exception as exc:
                                prefetched_errors[art_key] = exc
                            self.set_build_progress((done_count / len(future_to_art)) * 45, f"Downloading artwork {done_count} of {len(future_to_art)}...", "")
                    for task_number, art_key in task_art_names.items():
                        if art_key in downloaded_art:
                            prefetched_images[task_number] = downloaded_art[art_key]
                        elif art_key in prefetched_errors:
                            prefetched_errors[task_number] = prefetched_errors[art_key]
            for index, (entry, size_name, rule) in enumerate(tasks, start=1):
                if self.cancel_build_requested:
                    summary = f"Cancelled. Created {made} thumbnails before stopping."
                    self.set_build_progress((index - 1) / total * 100, summary, f"Partial output saved to:\n{run_dir}")
                    return
                progress_base = 45 if prefetched_images else 0
                progress_span = 55 if prefetched_images else 100
                self.set_build_progress(progress_base + ((index - 1) / total) * progress_span, f"Converting {index} of {total}: {clean_title(entry.title)}", "")
                try:
                    w, h, folder_name = self.size_details(size_name)
                    output_root = run_dir / folder_name
                    crop = self.build_crop() if not rule else CropSettings(**(rule.crop or {}))
                    if rule:
                        if rule.provider == "Local Image":
                            image = Image.open(rule.local_path)
                        else:
                            provider = rule.provider
                            libretro_source = rule.source or self.build_libretro_source_var.get()
                            result = self.providers.search(provider, rule.title, libretro_source=libretro_source)
                            image = Image.open(io.BytesIO(result.image_data))
                    else:
                        if index in prefetched_images:
                            image = Image.open(io.BytesIO(prefetched_images[index]))
                        elif index in prefetched_errors:
                            # A game-code match whose CDN object is missing/invalid
                            # gets one title-based attempt. That search uses the same
                            # Libretro-first, TheGamesDB-fallback provider path.
                            direct_error = prefetched_errors[index]
                            try:
                                result = self.providers.search(
                                    "Libretro",
                                    entry.title,
                                    libretro_source=self.build_libretro_source_var.get(),
                                    system=DEFAULT_SYSTEM,
                                )
                                image = Image.open(io.BytesIO(result.image_data))
                            except Exception as fallback_error:
                                raise LookupError(
                                    f"Direct Libretro artwork was unavailable ({direct_error}); "
                                    f"title-based Libretro/TheGamesDB fallback also failed: {fallback_error}"
                                ) from fallback_error
                        elif self.build_provider_var.get() == "Libretro":
                            result = self.providers.search(self.build_provider_var.get(), entry.title, libretro_source=self.build_libretro_source_var.get())
                            image = Image.open(io.BytesIO(result.image_data))
                        else:
                            result = self.providers.search(self.build_provider_var.get(), entry.title, libretro_source=self.build_libretro_source_var.get())
                            image = Image.open(io.BytesIO(result.image_data))
                    thumb = crop_image(image, (w, h), crop)
                    write_ezflash_bmp(thumb, output_path_for_code(output_root, entry.code))
                    made += 1
                except Exception as exc:
                    missed += 1
                    failed += 1
                self.set_build_progress(progress_base + (index / total) * progress_span, f"Converting {index} of {total}: {clean_title(entry.title)}", "")
            if self.cancel_build_requested:
                summary = f"Cancelled. Created {made} thumbnails before stopping."
                self.set_build_progress(100, summary, f"Partial output saved to:\n{run_dir}")
                return
            summary = f"Success. Created {made} thumbnails."
            if missed:
                summary += f" {missed} could not be found."
            self.set_build_progress(100, summary, f"Output saved to:\n{run_dir}")
            self.after(0, lambda: messagebox.showinfo(APP_NAME, f"{summary}\n\nOutput saved to:\n{run_dir}"))
        except Exception as exc:
            self.set_build_progress(0, f"Build failed: {exc}", "")
            self.after(0, lambda exc=exc: messagebox.showwarning(APP_NAME, str(exc)))
        finally:
            self.running = False
            def finish_build_ui():
                if hasattr(self, "build_button"):
                    self.build_button.configure(state="normal")
                if hasattr(self, "cancel_build_button"):
                    self.cancel_build_button.configure(state="normal")
                    self.cancel_build_button.pack_forget()
                if hasattr(self, "build_progress"):
                    self.build_progress.pack_forget()
            self.after(0, finish_build_ui)

    def _provider_credentials_snapshot(self) -> tuple[str, ...]:
        names = ("tgdb_key_var", "ss_dev_id_var", "ss_dev_pass_var", "ss_user_var", "ss_pass_var", "igdb_client_var", "igdb_secret_var")
        return tuple(getattr(self, name).get().strip() for name in names)

    def _load_settings(self):
        if not self.config_path.exists():
            self._saved_provider_credentials = self._provider_credentials_snapshot()
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            for name in ("local_pack", "igdb_client", "igdb_secret", "igdb_token", "tgdb_key", "ss_dev_id", "ss_dev_pass", "ss_user", "ss_pass"):
                var = getattr(self, f"{name}_var", None)
                if var:
                    var.set(data.get(name, ""))
            if hasattr(self, "local_pack_priority_var"):
                self.local_pack_priority_var.set(bool(data.get("local_pack_priority", False)))
            if data.get("build_provider") in PROVIDER_VALUES:
                self.build_provider_var.set(data["build_provider"])
            if data.get("custom_output_layout") in {"Mirror ROM folders", "Legacy CUSTOM"}:
                self.custom_output_layout_var.set(data["custom_output_layout"])
            if data.get("preview_provider") in PROVIDER_VALUES:
                self.preview_provider_var.set(data["preview_provider"])
            if data.get("preview_system") in LIBRETRO_SYSTEMS:
                self.preview_system_var.set(data["preview_system"])
            legacy_source = data.get("libretro_source")
            build_source = data.get("build_libretro_source", legacy_source)
            preview_source = data.get("preview_libretro_source", legacy_source)
            if build_source in LIBRETRO_SOURCE_FOLDERS:
                self.build_libretro_source_var.set(build_source)
            if preview_source in LIBRETRO_SOURCE_FOLDERS:
                self.preview_libretro_source_var.set(preview_source)
            region_order = [region for region in data.get("region_order", []) if region in REGION_ORDER]
            if region_order:
                self.region_order = region_order + [region for region in REGION_ORDER if region not in region_order]
            enabled = data.get("region_enabled")
            if isinstance(enabled, dict):
                self.region_enabled = {
                    region: bool(enabled.get(region, True))
                    for region in REGION_ORDER
                }
            rom_enabled = data.get("rom_region_enabled")
            if isinstance(rom_enabled, dict):
                for region, var in self.rom_region_vars.items():
                    var.set(bool(rom_enabled.get(region, True)))
            self.refresh_region_lists()
            loaded = []
            for item in data.get("exceptions", []):
                item.setdefault("size", "80x80")
                item.setdefault("source", "")
                loaded.append(ExceptionRule(**item))
            self.exceptions = loaded
            self.refresh_exceptions()
            custom_loaded = []
            for item in data.get("custom_art", data.get("custom_roms", [])):
                item.setdefault("rom_path", "")
                item.setdefault("rom_relative_path", "")
                item.setdefault("title", item.get("new_code", ""))
                item.setdefault("old_code", "----")
                item.setdefault("new_code", item.get("title", ""))
                item.setdefault("image_path", "")
                item.setdefault("size", "80x80")
                item.setdefault("system", system_for_path(Path(item["rom_path"])) if item["rom_path"] else "")
                try:
                    item["new_code"] = validate_custom_art_name(item["new_code"])
                    custom_loaded.append(CustomRomItem(**item))
                except (TypeError, ValueError):
                    pass
            self.custom_roms = custom_loaded
            self.refresh_custom_roms()
            self.update_local_pack_label()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        self._saved_provider_credentials = self._provider_credentials_snapshot()

    def save_settings(self):
        local_pack_priority_var = getattr(self, "local_pack_priority_var", None)
        data = {
            "local_pack": self.local_pack_var.get(),
            "local_pack_priority": bool(local_pack_priority_var.get()) if local_pack_priority_var is not None else False,
            "build_provider": self.build_provider_var.get(),
            "preview_provider": self.preview_provider_var.get(),
            "preview_system": self.preview_system_var.get(),
            "build_libretro_source": self.build_libretro_source_var.get(),
            "preview_libretro_source": self.preview_libretro_source_var.get(),
            "region_order": self.region_order,
            "region_enabled": self.region_enabled,
            "rom_region_enabled": {region: var.get() for region, var in self.rom_region_vars.items()},
            "igdb_client": self.igdb_client_var.get(),
            "igdb_secret": self.igdb_secret_var.get(),
            # Keep the older manually supplied token in the settings file for
            # backward compatibility; new usage relies on Client ID + Secret.
            "igdb_token": self.igdb_token_var.get(),
            "tgdb_key": self.tgdb_key_var.get(),
            "ss_dev_id": self.ss_dev_id_var.get(),
            "ss_dev_pass": self.ss_dev_pass_var.get(),
            "ss_user": self.ss_user_var.get(),
            "ss_pass": self.ss_pass_var.get(),
            "exceptions": [asdict(item) for item in self.exceptions],
            "custom_art": [asdict(item) for item in self.custom_roms],
            "custom_output_layout": self.custom_output_layout_var.get(),
        }
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Preserve provider metadata caches for ordinary UI preference changes.
        # Invalidate them only when the provider credentials actually change; the
        # region controls can be clicked frequently and must not force new requests.
        saved_credentials = getattr(self, "_saved_provider_credentials", None)
        current_credentials = self._provider_credentials_snapshot()
        providers = getattr(self, "providers", None)
        if providers is not None and saved_credentials is not None and current_credentials != saved_credentials:
            providers._igdb_access_token = ""
            providers._igdb_token_expires_at = 0.0
            providers._igdb_platform_ids.clear()
            providers._igdb_platform_catalog = None
            providers._screenscraper_system_records = None
        self._saved_provider_credentials = current_credentials
        self.status_var.set("Saved.")


if __name__ == "__main__":
    ThumbnailScraperApp().mainloop()
