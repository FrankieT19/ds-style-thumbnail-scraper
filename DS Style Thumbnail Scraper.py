from __future__ import annotations

import json
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
import io
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from ezflash_gba_full_library import load_gba_library
from ezflash_gba_pack_converter import build_art_index, find_best_art, iter_art_files
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
LIBRETRO_API_TREE = (
    "https://api.github.com/repos/libretro-thumbnails/"
    "Nintendo_-_Game_Boy_Advance/git/trees/master?recursive=1"
)
LIBRETRO_RAW_BY_FOLDER = (
    "https://raw.githubusercontent.com/libretro-thumbnails/"
    "Nintendo_-_Game_Boy_Advance/master/{folder}/{name}"
)
LIBRETRO_SOURCE_FOLDERS = {
    "Box Art": "Named_Boxarts",
    "Gameplay Screenshot": "Named_Snaps",
    "Title Screen": "Named_Titles",
}
LIBRETRO_SOURCE_CACHE_FILES = {
    "Named_Boxarts": "libretro_gba_boxarts.json",
    "Named_Snaps": "libretro_gba_snaps.json",
    "Named_Titles": "libretro_gba_titles.json",
}
GBA_TITLE_OFFSET = 0xA0
GBA_CODE_OFFSET = 0xAC
GBA_HEADER_CHECKSUM_OFFSET = 0xBD
GBA_HEADER_MIN_SIZE = 0xC0
WEB_HEADERS = {
    "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {APP_NAME}/1.3",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def libretro_source_cache_path(base_dir: Path, folder: str) -> Path:
    filename = LIBRETRO_SOURCE_CACHE_FILES.get(folder, f"libretro_gba_{folder.lower()}.json")
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


def fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or WEB_HEADERS)
    try:
        return urllib.request.urlopen(request, timeout=30).read()
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise LookupError("The image host refused the download (403 Forbidden). Try another result/provider, or try again later.") from exc
        raise


def title_regions(title: str) -> set[str]:
    regions: set[str] = set()
    if "USA" in title:
        regions.add("USA")
    if "Europe" in title:
        regions.add("Europe")
    if "Japan" in title:
        regions.add("Japan")
    other_markers = ("Australia", "World", "China", "Korea", "Asia", "Taiwan", "Hong Kong")
    if any(marker in title for marker in other_markers):
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
    rank = 0
    if "Virtual Console" in title:
        rank += 2
    if any(marker in title for marker in ("(Proto", "(Beta", "(Demo")):
        rank += 3
    if "(Alt)" in title:
        rank += 4
    return rank


def provider_key(provider: str) -> str:
    if provider.startswith("IGDB"):
        return "IGDB"
    if provider.startswith("TheGamesDB"):
        return "TheGamesDB"
    if provider.startswith("ScreenScraper"):
        return "ScreenScraper"
    return provider


def load_libretro_source_index(cache_path: Path, folder: str, refresh: bool = False) -> list[str]:
    if cache_path.exists() and not refresh:
        cached_names = json.loads(cache_path.read_text(encoding="utf-8"))
        if len(cached_names) > 1000:
            return cached_names
    data = json.loads(http_get(LIBRETRO_API_TREE).decode("utf-8"))
    prefix = f"{folder}/"
    names = sorted(
        Path(item["path"]).name
        for item in data.get("tree", [])
        if item.get("path", "").startswith(prefix)
        and item.get("path", "").lower().endswith(".png")
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(names, indent=2), encoding="utf-8")
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


def validate_custom_art_name(value: str) -> str:
    name = value.strip()
    if name.lower().endswith(".bmp"):
        name = name[:-4].rstrip()
    if not name:
        raise ValueError("Enter the ROM or folder name, or select the ROM file.")
    if any(ch in name for ch in '<>:"/\\|?*'):
        raise ValueError('Custom art names cannot contain: < > : " / \\ | ? *')
    if len(name) > 96:
        raise ValueError("Custom art names must be 96 characters or fewer.")
    return name


def output_path_for_custom_name(output_root: Path, name: str) -> Path:
    return output_root / "CUSTOM" / f"{validate_custom_art_name(name)}.bmp"


class Providers:
    def __init__(self, app: "ThumbnailScraperApp"):
        self.app = app
        self.libretro_indexes: dict[str, list[str]] = {}
        self.libretro_direct_indexes: dict[str, tuple[dict[str, str], list[str]]] = {}
        self.local_art_index = None

    def search(self, provider: str, query: str, libretro_source: str | None = None) -> ProviderResult:
        results = self.search_many(provider, query, max_results=1, libretro_source=libretro_source)
        if not results:
            raise LookupError("No artwork found.")
        return results[0]

    def search_many(self, provider: str, query: str, max_results: int | None = 20, libretro_source: str | None = None) -> list[ProviderResult]:
        provider = provider_key(provider)
        if provider == "Libretro":
            return self.search_libretro_many(query, max_results, libretro_source)
        if provider == "Local Pack":
            return self.search_local_pack_many(query, max_results)
        if provider == "IGDB":
            return self.search_igdb_many(query, max_results)
        if provider == "TheGamesDB":
            return self.search_thegamesdb_many(query, max_results)
        if provider == "ScreenScraper":
            return self.search_screenscraper_many(query, max_results)
        raise ValueError(f"Unknown provider: {provider}")

    def search_libretro_many(self, query: str, max_results: int | None = 20, libretro_source: str | None = None) -> list[ProviderResult]:
        folder = LIBRETRO_SOURCE_FOLDERS.get(libretro_source or self.app.preview_libretro_source_var.get(), "Named_Boxarts")
        if folder not in self.libretro_indexes:
            cache = libretro_source_cache_path(self.app.base_dir, folder)
            self.libretro_indexes[folder] = load_libretro_source_index(cache, folder)
        libretro_index = self.libretro_indexes[folder]
        search_queries = self.libretro_search_queries(query)
        query_content = content_tokens(query)
        scored = []
        for name in libretro_index:
            if not self.app.region_allowed(name):
                continue
            name_content = content_tokens(name)
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
        scored.sort(key=lambda item: (self.app.region_priority(item[1]), -item[0], variant_rank(item[1]), item[1]))
        if not scored:
            allowed_index = sorted(
                [name for name in libretro_index if self.app.region_allowed(name)],
                key=lambda name: (self.app.region_priority(name), name),
            )
            for search_query in search_queries:
                fake = type("FakeRom", (), {"path": Path(f"{search_query}.gba"), "title": search_query, "code": "----"})()
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
                        LIBRETRO_RAW_BY_FOLDER.format(folder=folder, name=urllib.parse.quote(art_name)),
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
                    results.append(ProviderResult("Libretro", art_name, fetched[art_name]))
        else:
            for art_name in art_names:
                url_name = urllib.parse.quote(art_name)
                url = LIBRETRO_RAW_BY_FOLDER.format(folder=folder, name=url_name)
                results.append(ProviderResult("Libretro", art_name, http_get(url)))
        if not results:
            raise LookupError("No Libretro box art match found.")
        return results

    def direct_libretro_result(self, entry, libretro_source: str) -> ProviderResult:
        folder, art_name = self.direct_libretro_art_name(entry, libretro_source)
        url_name = urllib.parse.quote(art_name)
        url = LIBRETRO_RAW_BY_FOLDER.format(folder=folder, name=url_name)
        return ProviderResult("Libretro", art_name, http_get(url))

    def direct_libretro_art_map(self, libretro_source: str) -> dict[str, tuple[str, str]]:
        folder = LIBRETRO_SOURCE_FOLDERS.get(libretro_source, "Named_Boxarts")
        if folder not in self.libretro_indexes:
            cache = libretro_source_cache_path(self.app.base_dir, folder)
            self.libretro_indexes[folder] = load_libretro_source_index(cache, folder)

        cache_key = f"{folder}|{'|'.join(self.app.ordered_regions())}"
        if cache_key not in self.libretro_direct_indexes:
            allowed_index = sorted(
                [name for name in self.libretro_indexes[folder] if self.app.region_allowed(name)],
                key=lambda name: (self.app.region_priority(name), name),
            )
            exact_index = {}
            for name in allowed_index:
                exact_index.setdefault(normalize_for_match(name), name)
            self.libretro_direct_indexes[cache_key] = (exact_index, allowed_index)

        exact_index, _allowed_index = self.libretro_direct_indexes[cache_key]
        art_by_code_root: dict[str, tuple[str, str]] = {}
        for entry in sorted(self.app.get_game_library(), key=lambda item: (self.app.region_priority(item.title), item.title)):
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
        if folder not in self.libretro_indexes:
            cache = libretro_source_cache_path(self.app.base_dir, folder)
            self.libretro_indexes[folder] = load_libretro_source_index(cache, folder)

        cache_key = f"{folder}|{'|'.join(self.app.ordered_regions())}"
        if cache_key not in self.libretro_direct_indexes:
            allowed_index = sorted(
                [name for name in self.libretro_indexes[folder] if self.app.region_allowed(name)],
                key=lambda name: (self.app.region_priority(name), name),
            )
            exact_index = {}
            for name in allowed_index:
                exact_index.setdefault(normalize_for_match(name), name)
            self.libretro_direct_indexes[cache_key] = (exact_index, allowed_index)

        exact_index, allowed_index = self.libretro_direct_indexes[cache_key]
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
            for entry in sorted(library, key=lambda item: (self.app.region_priority(item.title), item.title)):
                if entry.code[:3] in matched_code_roots and self.app.region_allowed(entry.title):
                    queries.append(entry.title)

        return list(dict.fromkeys(queries))

    def search_local_pack_many(self, query: str, max_results: int | None = 20) -> list[ProviderResult]:
        pack = self.app.local_pack_var.get().strip()
        if not pack:
            raise LookupError("Choose a local art pack folder first.")
        pack_path = Path(pack)
        if self.local_art_index is None:
            primary, europe = iter_art_files(pack_path)
            self.local_art_index = build_art_index(primary + europe)
        candidates = []
        for arts in self.local_art_index.values():
            for art in arts:
                if not self.app.region_allowed(self.local_art_region_text(art)):
                    continue
                score = title_match_score(query, art.title)
                if score >= 2.2 and title_search_compatible(query, art.title):
                    candidates.append((score, art))
        candidates.sort(
            key=lambda item: (
                self.app.region_priority(self.local_art_region_text(item[1])),
                -item[0],
                variant_rank(item[1].path.name),
                item[1].path.name,
            ),
        )
        if not candidates:
            art = find_best_art(query, self.local_art_index)
            candidates = [(99, art)] if art and self.app.region_allowed(self.local_art_region_text(art)) else []
        limit = len(candidates) if max_results is None else max_results
        results = [
            ProviderResult("Local Pack", self.local_art_label(art, pack_path), art.path.read_bytes())
            for _score, art in candidates[:limit]
            if art
        ]
        if not results:
            raise LookupError("No local art match found.")
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

    def search_igdb_many(self, query: str, max_results: int = 20) -> list[ProviderResult]:
        client_id = self.app.igdb_client_var.get().strip()
        token = self.app.igdb_token_var.get().strip()
        if not client_id or not token:
            raise LookupError("IGDB needs a Client ID and bearer access token.")
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        safe_query = query.replace('"', '\\"')
        body = (
            "fields name,cover.image_id,artworks.image_id;"
            f' search "{safe_query}";'
            f" where platforms = ({GBA_IGDB_PLATFORM_ID}); limit 10;"
        )
        games = post_json("https://api.igdb.com/v4/games", body, headers)
        results = []
        for game in games:
            image_ids = []
            if game.get("artworks"):
                image_ids.extend(item.get("image_id") for item in game["artworks"] if item.get("image_id"))
            if game.get("cover") and game["cover"].get("image_id"):
                image_ids.append(game["cover"]["image_id"])
            for image_id in image_ids[:5]:
                url = f"https://images.igdb.com/igdb/image/upload/t_720p/{image_id}.jpg"
                results.append(ProviderResult("IGDB", f"{game.get('name', query)} - {image_id}", fetch_bytes(url)))
                if len(results) >= max_results:
                    return results
        if not results:
            raise LookupError("No IGDB artwork found.")
        return results[:max_results]

    def search_thegamesdb_many(self, query: str, max_results: int = 20) -> list[ProviderResult]:
        api_key = self.app.tgdb_key_var.get().strip()
        if not api_key:
            raise LookupError("TheGamesDB needs an API key.")
        params = urllib.parse.urlencode(
            {
                "apikey": api_key,
                "name": query,
                "filter[platform]": "Game Boy Advance",
                "include": "boxart",
            }
        )
        data = request_json(f"https://api.thegamesdb.net/v1/Games/ByGameName?{params}", WEB_HEADERS)
        games = data.get("data", {}).get("games") or []
        include = data.get("include", {})
        boxart = include.get("boxart", {})
        base = boxart.get("base_url", {}).get("original") or boxart.get("base_url", {}).get("large") or ""
        images = boxart.get("data") or boxart.get("images") or {}
        results = []
        for game in games:
            game_id = str(game.get("id"))
            game_images = images.get(game_id) or []
            for image in game_images:
                filename = image.get("filename") or image.get("thumb")
                if filename:
                    results.append(ProviderResult("TheGamesDB", f"{game.get('game_title', query)} - {filename}", fetch_bytes(base + filename)))
                    if len(results) >= max_results:
                        return results
        if not results:
            raise LookupError("No TheGamesDB box art found.")
        return results[:max_results]

    def search_screenscraper_many(self, query: str, max_results: int = 20) -> list[ProviderResult]:
        devid = self.app.ss_dev_id_var.get().strip()
        devpassword = self.app.ss_dev_pass_var.get().strip()
        ssid = self.app.ss_user_var.get().strip()
        sspassword = self.app.ss_pass_var.get().strip()
        if not devid or not devpassword:
            raise LookupError("ScreenScraper needs developer credentials. This is an advanced/paid provider.")
        if not ssid or not sspassword:
            raise LookupError("ScreenScraper needs your username and password as well as developer credentials.")
        params = urllib.parse.urlencode(
            {
                "devid": devid,
                "devpassword": devpassword,
                "softname": APP_NAME,
                "ssid": ssid,
                "sspassword": sspassword,
                "systemeid": GBA_SCREENSCRAPER_SYSTEM_ID,
                "recherche": query,
                "output": "json",
            }
        )
        results = []
        data = request_json(f"https://www.screenscraper.fr/api2/jeuRecherche.php?{params}", WEB_HEADERS)
        games = data.get("response", {}).get("jeux", {}).get("jeu") or []
        if isinstance(games, dict):
            games = [games]
        for game in games:
            medias = game.get("medias", {}).get("media", [])
            if isinstance(medias, dict):
                medias = [medias]
            title = game.get("nom") or query
            for preferred in ("box-2D", "steamgrid", "sstitle", "screenmarquee"):
                for media in medias:
                    if media.get("type") == preferred and media.get("url"):
                        results.append(ProviderResult("ScreenScraper", f"{title} - {preferred}", fetch_bytes(media["url"])))
                        if len(results) >= max_results:
                            return results
        if not results:
            raise LookupError("No ScreenScraper media found.")
        return results[:max_results]


def crop_image(image: Image.Image, size: tuple[int, int], crop: CropSettings) -> Image.Image:
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
        self.geometry("1180x830")
        self.minsize(1040, 770)
        self.base_dir = app_dir()
        self._seed_bundled_cache()
        self._set_window_icon()
        self.config_path = self.base_dir / CONFIG_NAME
        self.providers = Providers(self)
        self.current_result: ProviderResult | None = None
        self.result_options: list[ProviderResult] = []
        self.current_source_image: Image.Image | None = None
        self.build_result: ProviderResult | None = None
        self.build_source_image: Image.Image | None = None
        self.current_local_path = ""
        self.preview_photo = None
        self.build_preview_photo = None
        self.result_thumbs = []
        self.game_names: list[str] = []
        self.game_library = []
        self.known_game_codes: set[str] = set()
        self.suggestion_box: tk.Listbox | None = None
        self.region_listboxes: list[tk.Listbox] = []
        self.exceptions: list[ExceptionRule] = []
        self.custom_roms: list[CustomRomItem] = []
        self.custom_preview_photo = None
        self.running = False
        self.cancel_build_requested = False
        self.loading_custom_crop = False

        self.build_provider_var = tk.StringVar(value="Libretro")
        self.preview_provider_var = tk.StringVar(value="Libretro")
        self.build_libretro_source_var = tk.StringVar(value="Box Art")
        self.preview_libretro_source_var = tk.StringVar(value="Box Art")
        self.size_var = tk.StringVar(value="80x80")
        self.search_var = tk.StringVar(value=DEFAULT_SEARCH)
        self.result_choice_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.build_status_var = tk.StringVar(value="Ready to build.")
        self.build_output_var = tk.StringVar(value="")
        self.build_progress_var = tk.DoubleVar(value=0.0)
        self.local_pack_var = tk.StringVar()
        self.igdb_client_var = tk.StringVar()
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

    def _build_region_order_control(self, parent):
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
        ttk.Button(frame, text="Move Up", command=lambda lb=region_list: self.move_region(lb, -1)).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        ttk.Button(frame, text="Move Down", command=lambda lb=region_list: self.move_region(lb, 1)).grid(row=1, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(frame, text="Enable/Disable", command=lambda lb=region_list: self.toggle_region(lb)).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))
        region_list.bind("<space>", lambda _event, lb=region_list: self.toggle_region(lb))
        region_list.bind("<Double-Button-1>", lambda _event, lb=region_list: self.toggle_region(lb))
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
        ttk.Label(title_box, text="Build EZ Flash Omega DE thumbnail packs from online or local artwork.", style="Sub.TLabel").pack(anchor="w", pady=(3, 0))
        version_box = ttk.Frame(header, style="TFrame")
        version_box.pack(side="right", anchor="n")
        ttk.Label(version_box, text="DS Style Thumbnail Scraper v1.3", style="HeaderVersion.TLabel").pack(anchor="e")
        ttk.Label(version_box, text="For DS Style v6.6", style="HeaderVersion.TLabel").pack(anchor="e", pady=(4, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.build_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        self.preview_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        self.custom_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        self.exceptions_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=14)
        notebook.add(self.build_tab, text="Build Pack")
        notebook.add(self.preview_tab, text="Search & Preview")
        notebook.add(self.custom_tab, text="Custom Art")
        notebook.add(self.exceptions_tab, text="Exceptions")
        notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self._build_build_tab()
        self._build_preview_tab()
        self._build_custom_tab()
        self._build_exceptions_tab()

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
        ttk.Label(source_options, text="Main source").pack(anchor="w", pady=(14, 4))
        build_provider_combo = ttk.Combobox(source_options, textvariable=self.build_provider_var, values=PROVIDER_VALUES, state="readonly", width=20)
        build_provider_combo.pack(anchor="w")
        build_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_build_source_change())
        ttk.Label(source_options, text="Libretro source").pack(anchor="w", pady=(14, 4))
        source_combo = ttk.Combobox(source_options, textvariable=self.build_libretro_source_var, values=list(LIBRETRO_SOURCE_FOLDERS), state="readonly", width=20)
        source_combo.pack(anchor="w")
        source_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_build_source_change())
        ttk.Label(source_options, text="Local pack").pack(anchor="w", pady=(14, 4))
        ttk.Button(source_options, text="Choose Folder...", command=self.choose_local_pack).pack(anchor="w")
        self.local_pack_label = ttk.Label(source_options, text="No local pack selected", style="Muted.TLabel", wraplength=190)
        self.local_pack_label.pack(anchor="w", pady=(6, 0))
        ttk.Label(source_options, text="Thumbnail size").pack(anchor="w", pady=(14, 4))
        build_size_combo = ttk.Combobox(source_options, textvariable=self.size_var, values=["80x80", "120x80"], state="readonly", width=20)
        build_size_combo.pack(anchor="w")
        build_size_combo.bind("<<ComboboxSelected>>", lambda _event: (self.update_build_preview(), self.update_preview()))
        ttk.Checkbutton(source_options, text="Build exceptions only", variable=self.exceptions_only_var).pack(anchor="w", pady=(14, 0))
        self.build_button = ttk.Button(source_options, text="Build Thumbnail Pack", style="Accent.TButton", command=self.build_pack)
        self.build_button.pack(anchor="w", pady=(22, 0))
        self.cancel_build_button = ttk.Button(source_options, text="Cancel Building", command=self.cancel_build)
        self.cancel_build_button.pack(anchor="w", pady=(8, 0))
        self.cancel_build_button.pack_forget()

        ttk.Label(region_options, text="Regions", style="Section.TLabel").pack(anchor="w")
        ttk.Label(region_options, text="Game regions to build").pack(anchor="w", pady=(14, 4))
        ttk.Label(region_options, text="Choose which game regions your pack should support.", style="Muted.TLabel", wraplength=210).pack(anchor="w", pady=(0, 6))
        self._build_rom_region_control(region_options)
        ttk.Label(region_options, text="Artwork priority").pack(anchor="w", pady=(14, 4))
        ttk.Label(region_options, text="Choose the order artwork is tried in. If the first region is missing, the next available one is used.", style="Muted.TLabel", wraplength=210).pack(anchor="w", pady=(0, 6))
        self._build_region_order_control(region_options)

        middle = ttk.Frame(self.build_tab, style="Panel.TFrame")
        middle.pack(side="left", fill="y", padx=(0, 18))
        ttk.Label(middle, text="Current Look", style="Section.TLabel").pack(anchor="w")
        self.build_preview_label = tk.Label(middle, bg="#101a29", fg="#aebfd2", text="Loading preview...", width=42, height=12, font=("Segoe UI", 10))
        self.build_preview_label.pack(anchor="w", pady=(10, 8))
        self.build_preview_info = ttk.Label(middle, text="Loading current look...", style="Muted.TLabel")
        self.build_preview_info.pack(anchor="w")
        ttk.Label(middle, text="Pack Crop", style="Section.TLabel").pack(anchor="w", pady=(16, 6))
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
        ttk.Label(controls, text="Source").pack(anchor="w", pady=(10, 4))
        preview_provider_combo = ttk.Combobox(controls, textvariable=self.preview_provider_var, values=PROVIDER_VALUES, state="readonly", width=24)
        preview_provider_combo.pack(anchor="w")
        preview_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_preview_source_change())
        ttk.Label(controls, text="Libretro source").pack(anchor="w", pady=(12, 4))
        preview_source_combo = ttk.Combobox(controls, textvariable=self.preview_libretro_source_var, values=list(LIBRETRO_SOURCE_FOLDERS), state="readonly", width=24)
        preview_source_combo.pack(anchor="w")
        preview_source_combo.bind("<<ComboboxSelected>>", lambda _event: self.on_preview_source_change())
        ttk.Button(controls, text="Choose Local Pack...", command=self.choose_local_pack).pack(anchor="w", pady=(10, 0))
        ttk.Label(controls, text="Thumbnail size").pack(anchor="w", pady=(12, 4))
        size_combo = ttk.Combobox(controls, textvariable=self.size_var, values=["80x80", "120x80"], state="readonly", width=24)
        size_combo.pack(anchor="w")
        size_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_preview())
        ttk.Label(controls, text="Artwork priority").pack(anchor="w", pady=(12, 4))
        ttk.Label(controls, text="Choose the order artwork appears in preview results.", style="Muted.TLabel", wraplength=210).pack(anchor="w", pady=(0, 6))
        self._build_region_order_control(controls)
        ttk.Label(controls, text="Game").pack(anchor="w", pady=(12, 4))
        self.search_entry = ttk.Entry(controls, textvariable=self.search_var, width=34)
        self.search_entry.pack(anchor="w", pady=(10, 4))
        self.search_entry.bind("<KeyRelease>", self.update_suggestions)
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
        self.search_button = ttk.Button(controls, text="Fetch Preview", style="Accent.TButton", command=self.preview_search)
        self.search_button.pack(anchor="w")
        ttk.Label(controls, text="Artwork").pack(anchor="w", pady=(12, 4))
        ttk.Button(controls, text="Use Local Image...", command=self.choose_preview_local).pack(anchor="w", pady=(8, 0))
        ttk.Button(controls, text="Add As Exception", command=self.add_exception).pack(anchor="w", pady=(8, 0))

        preview = ttk.Frame(self.preview_tab, style="Panel.TFrame")
        preview.grid(row=0, column=1, sticky="nsew", padx=(0, 20))
        ttk.Label(preview, text="Thumbnail Preview", style="Section.TLabel").pack(anchor="w")
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
        ttk.Label(results, text="Provider Results", style="Section.TLabel").pack(anchor="w")
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
        ttk.Label(self.custom_tab, text="Custom Thumbnail Overrides", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.custom_tab,
            text="Add artwork for ROM hacks, homebrew, folders, translations, or games missing from the normal lookup. ROM files are not edited.",
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
        for column, text, width in (("name", "Thumbnail name", 230), ("source", "Source", 120), ("size", "Size", 76), ("image", "Image", 170)):
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
        ttk.Button(actions, text="Add ROM...", command=self.add_custom_roms).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Button(actions, text="Enter Name...", command=self.add_custom_name).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Button(actions, text="Set Image...", command=self.set_custom_image).pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Button(actions, text="Remove Selected", command=self.remove_custom_roms).pack(anchor="w", fill="x", pady=(0, 16))
        ttk.Label(actions, text="Thumbnail size").pack(anchor="w")
        custom_size_combo = ttk.Combobox(actions, textvariable=self.size_var, values=["80x80", "120x80"], state="readonly", width=18)
        custom_size_combo.pack(anchor="w", fill="x", pady=(4, 12))
        custom_size_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_custom_size_to_selection())
        ttk.Label(actions, text="Selected name").pack(anchor="w")
        self.custom_code_var = tk.StringVar()
        ttk.Entry(actions, textvariable=self.custom_code_var, width=22).pack(anchor="w", fill="x", pady=(4, 8))
        ttk.Label(actions, text="Must exactly match the ROM filename without .gba, or the folder name.", style="Muted.TLabel", wraplength=170).pack(anchor="w", pady=(0, 8))
        ttk.Button(actions, text="Apply Name", command=self.apply_custom_code).pack(anchor="w", fill="x", pady=(0, 16))
        ttk.Button(actions, text="Build Custom Art", style="Accent.TButton", command=self.build_custom_rom_output).pack(anchor="w", fill="x")

        right = ttk.Frame(body, style="Panel.TFrame")
        right.grid(row=0, column=2, sticky="nw")
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Selected Preview", style="Section.TLabel").pack(anchor="w")
        self.custom_preview_label = tk.Label(right, bg="#101a29", width=300, height=210)
        self.custom_preview_label.pack_propagate(False)
        self.custom_preview_label.pack(anchor="w", pady=(8, 6))
        self.custom_preview_info = ttk.Label(right, text="Choose a ROM and image", style="Muted.TLabel", wraplength=340)
        self.custom_preview_info.pack(anchor="w")
        crop_row = ttk.Frame(right, style="Panel.TFrame")
        crop_row.pack(anchor="w", pady=(12, 0))
        for label, var, from_, to in (("Zoom", self.custom_zoom_var, 1.0, 3.0), ("Move X", self.custom_crop_x_var, -100, 100), ("Move Y", self.custom_crop_y_var, -100, 100)):
            control = ttk.Frame(crop_row, style="Panel.TFrame")
            control.pack(side="left", padx=(0, 10))
            ttk.Label(control, text=label).pack(anchor="w")
            tk.Scale(control, variable=var, from_=from_, to=to, resolution=0.05 if label == "Zoom" else 1, orient="horizontal", length=120, bg="#152235", fg="#edf4fb", troughcolor="#101a29", activebackground="#263a57", highlightthickness=0, command=lambda _v: self.on_custom_crop_changed()).pack(anchor="w")

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
        ttk.Label(self.settings_tab, text="Provider Credentials", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        fields = [
            ("Local pack folder", self.local_pack_var, "folder", False),
            ("IGDB Client ID", self.igdb_client_var, None, False),
            ("IGDB access token", self.igdb_token_var, None, False),
            ("TheGamesDB API key", self.tgdb_key_var, None, False),
            ("ScreenScraper developer ID", self.ss_dev_id_var, None, False),
            ("ScreenScraper developer password", self.ss_dev_pass_var, None, True),
            ("ScreenScraper username", self.ss_user_var, None, False),
            ("ScreenScraper password", self.ss_pass_var, None, True),
        ]
        for row, (label, var, action, hidden) in enumerate(fields, start=1):
            ttk.Label(self.settings_tab, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(self.settings_tab, textvariable=var, width=54, show="*" if hidden else "").grid(row=row, column=1, sticky="w", padx=(10, 8))
            if action == "folder":
                ttk.Button(self.settings_tab, text="Browse", command=self.choose_local_pack).grid(row=row, column=2, sticky="w")
        ttk.Label(
            self.settings_tab,
            text="ScreenScraper is an advanced provider and requires developer credentials from ScreenScraper as well as a user account.",
            style="Muted.TLabel",
            wraplength=620,
        ).grid(row=len(fields) + 1, column=1, sticky="w", pady=(8, 0), padx=(10, 8))
        ttk.Button(self.settings_tab, text="Save Settings", style="Accent.TButton", command=self.save_settings).grid(row=len(fields) + 2, column=1, sticky="w", pady=(16, 0))

    def log(self, text: str):
        self.status_var.set(text)
        self.update_idletasks()

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

    def move_region(self, region_list: tk.Listbox, direction: int):
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
        self.save_settings()
        self.on_region_change()

    def toggle_region(self, region_list: tk.Listbox):
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
        self.save_settings()
        self.on_region_change()
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

    def on_region_change(self):
        self.hide_suggestions()
        self.build_preview_search()
        if self.search_var.get().strip():
            self.preview_search()

    def on_rom_region_change(self):
        self.save_settings()

    def on_build_source_change(self):
        self.save_settings()
        self.build_preview_search()

    def on_preview_source_change(self):
        self.save_settings()
        self.hide_suggestions()
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
        if len(query) < 2 or not self.game_names:
            self.hide_suggestions()
            return
        matches = [name for name in self.game_names if query in name.lower() and self.region_allowed(name)][:8]
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
        self.set_preview_loading(True)
        def worker():
            try:
                self.status_var.set("Fetching preview...")
                results = self.providers.search_many(
                    self.preview_provider_var.get(),
                    self.search_var.get(),
                    max_results=PREVIEW_RESULT_LIMIT,
                    libretro_source=self.preview_libretro_source_var.get(),
                )
                self.result_options = results
                result = results[0]
                image = Image.open(__import__("io").BytesIO(result.image_data))
                self.current_result = result
                self.current_source_image = image
                self.after(0, self.refresh_result_gallery)
            except Exception as exc:
                self.after(0, lambda: messagebox.showwarning(APP_NAME, str(exc)))
                self.status_var.set("Preview failed.")
            finally:
                self.after(0, lambda: self.set_preview_loading(False))
        threading.Thread(target=worker, daemon=True).start()

    def build_preview_search(self):
        if hasattr(self, "build_preview_info"):
            self.after(0, lambda: self.build_preview_info.configure(text="Loading current look..."))
        def worker():
            try:
                if not self.selected_regions():
                    raise LookupError("Choose at least one region.")
                self.status_var.set("Fetching build preview...")
                result = None
                last_error: Exception | None = None
                for query in self.build_preview_queries():
                    try:
                        result = self.providers.search(
                            self.build_provider_var.get(),
                            query,
                            libretro_source=self.build_libretro_source_var.get(),
                        )
                        break
                    except Exception as exc:
                        last_error = exc
                if result is None:
                    raise last_error or LookupError("No build preview artwork found.")
                image = Image.open(__import__("io").BytesIO(result.image_data))
                self.build_result = result
                self.build_source_image = image
                self.after(0, self.update_build_preview)
            except Exception as exc:
                self.after(0, lambda: messagebox.showwarning(APP_NAME, str(exc)))
                self.status_var.set("Build preview failed.")
        threading.Thread(target=worker, daemon=True).start()

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
                    image = Image.open(__import__("io").BytesIO(result.image_data))
                    thumb = crop_image(image, self.selected_size()[:2], self.current_crop()).resize((72, 72 if self.size_var.get() == "80x80" else 48), Image.Resampling.NEAREST)
                    photo = ImageTk.PhotoImage(thumb)
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
        self.current_result = ProviderResult("Local Image", Path(path).name, data)
        self.current_local_path = path
        self.result_options = [self.current_result]
        self.current_source_image = Image.open(path)
        self.refresh_result_gallery()

    def next_custom_code(self) -> str:
        used = {item.new_code for item in self.custom_roms}
        for prefix in ("Z", "X", "Q"):
            for number in range(1, 1000):
                code = f"{prefix}{number:03d}"
                if code not in used and code not in self.known_game_codes:
                    return code
        raise ValueError("Too many homebrew ROMs to auto-assign codes.")

    def add_custom_roms(self):
        paths = filedialog.askopenfilenames(filetypes=[("GBA ROMs", "*.gba *.agb *.bin"), ("All files", "*.*")])
        if not paths:
            return
        added = 0
        selected_size = self.size_var.get()
        existing_paths = {(item.rom_path, item.size) for item in self.custom_roms if item.rom_path}
        existing_names = {(item.new_code.casefold(), item.size) for item in self.custom_roms}
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
            if (thumb_name.casefold(), selected_size) in existing_names:
                continue
            self.custom_roms.append(CustomRomItem(str(path), title or path.stem, code or "----", thumb_name, size=selected_size))
            existing_paths.add((str(path), selected_size))
            existing_names.add((thumb_name.casefold(), selected_size))
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
        ttk.Label(dialog, text="ROM filename without .gba, or folder name").grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))
        name_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=name_var, width=42)
        entry.grid(row=1, column=0, sticky="ew", padx=16)
        ttk.Label(dialog, text="Example: Pokemon Emerald Rogue or Game Boy Advance", style="Muted.TLabel").grid(row=2, column=0, sticky="w", padx=16, pady=(6, 12))
        buttons = ttk.Frame(dialog, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="e", padx=16, pady=(0, 16))

        def add():
            try:
                name = validate_custom_art_name(name_var.get())
            except ValueError as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=dialog)
                return
            selected_size = self.size_var.get()
            if (name.casefold(), selected_size) in {(item.new_code.casefold(), item.size) for item in self.custom_roms}:
                messagebox.showinfo(APP_NAME, "That custom name and size is already in the list.", parent=dialog)
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
            source = Path(item.rom_path).name if item.rom_path else "Manual"
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
            messagebox.showinfo(APP_NAME, "Select one or more custom art entries first.")
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

    def apply_custom_code(self):
        indices = self.selected_custom_indices()
        if len(indices) != 1:
            messagebox.showinfo(APP_NAME, "Select one custom entry to edit its name.")
            return
        try:
            code = validate_custom_art_name(self.custom_code_var.get())
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return
        size = self.custom_roms[indices[0]].size
        used = {(item.new_code.casefold(), item.size) for index, item in enumerate(self.custom_roms) if index != indices[0]}
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
                self.custom_preview_info.configure(text="Choose a ROM and image")
            return
        item = self.custom_roms[indices[0]]
        self.custom_code_var.set(item.new_code)
        crop = self.crop_from_dict(item.crop)
        if not item.image_path:
            self.custom_preview_label.configure(image="", width=300, height=210)
            self.custom_preview_photo = None
            self.custom_preview_info.configure(text=f"{item.new_code}.bmp - no image set")
            return
        try:
            image = Image.open(item.image_path)
            w, h, _folder = self.size_details(item.size)
            thumb = crop_image(image, (w, h), crop)
            preview = thumb.resize((w * 3, h * 3), Image.Resampling.NEAREST)
            self.custom_preview_photo = ImageTk.PhotoImage(preview)
            self.custom_preview_label.configure(image=self.custom_preview_photo, width=w * 3, height=h * 3)
            folder_name = self.size_details(item.size)[2]
            self.custom_preview_info.configure(text=f"{folder_name}/CUSTOM/{item.new_code}.bmp ({item.size})")
        except OSError as exc:
            self.custom_preview_info.configure(text=f"Could not preview image: {exc}")

    def build_custom_rom_output(self):
        if not self.custom_roms:
            messagebox.showinfo(APP_NAME, "Add custom entries first.")
            return
        missing = [item.new_code for item in self.custom_roms if not item.image_path]
        if missing:
            messagebox.showwarning(APP_NAME, "Set images for every custom entry first.")
            return
        try:
            run_dir = self.output_run_dir()
            for item in self.custom_roms:
                thumb_name = validate_custom_art_name(item.new_code)
                image = Image.open(item.image_path)
                w, h, folder_name = self.size_details(item.size)
                imgs_dir = run_dir / folder_name
                thumb = crop_image(image, (w, h), self.crop_from_dict(item.crop))
                write_ezflash_bmp(thumb, output_path_for_custom_name(imgs_dir, thumb_name))
            self.status_var.set(f"Custom art output created: {run_dir}")
            messagebox.showinfo(APP_NAME, f"Custom art output created:\n{run_dir}")
        except Exception as exc:
            messagebox.showwarning(APP_NAME, str(exc))

    def update_preview(self):
        if not self.current_source_image:
            return
        w, h, _folder = self.selected_size()
        thumb = crop_image(self.current_source_image, (w, h), self.current_crop())
        preview = thumb.resize((w * 3, h * 3), Image.Resampling.NEAREST)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_label.configure(image=self.preview_photo, width=w * 3, height=h * 3)
        label = self.current_result.label if self.current_result else ""
        self.preview_info.configure(text=f"{self.preview_provider_var.get()} - {label} - {w}x{h}")
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
        if not self.current_result:
            messagebox.showinfo(APP_NAME, "Fetch or choose an image first.")
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
            normal_libretro_build = self.build_provider_var.get() == "Libretro"
            if normal_libretro_build:
                unique_art_urls = {}
                self.set_build_progress(0, "Matching artwork to games...", "")
                art_by_code_root = self.providers.direct_libretro_art_map(self.build_libretro_source_var.get())
                for task_number, (entry, _size_name, rule) in enumerate(tasks, start=1):
                    if rule:
                        continue
                    art_match = art_by_code_root.get(entry.code[:3] if entry.code else "")
                    if art_match:
                        folder, art_name = art_match
                        task_art_names[task_number] = (folder, art_name)
                        url_name = urllib.parse.quote(art_name)
                        unique_art_urls.setdefault(
                            (folder, art_name),
                            LIBRETRO_RAW_BY_FOLDER.format(folder=folder, name=url_name),
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
                                downloaded_art[art_key] = future.result()
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
                            raise prefetched_errors[index]
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

    def _load_settings(self):
        if not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            for name in ("local_pack", "igdb_client", "igdb_token", "tgdb_key", "ss_dev_id", "ss_dev_pass", "ss_user", "ss_pass"):
                var = getattr(self, f"{name}_var", None)
                if var:
                    var.set(data.get(name, ""))
            if data.get("build_provider") in PROVIDER_VALUES:
                self.build_provider_var.set(data["build_provider"])
            if data.get("preview_provider") in PROVIDER_VALUES:
                self.preview_provider_var.set(data["preview_provider"])
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
                item.setdefault("title", item.get("new_code", ""))
                item.setdefault("old_code", "----")
                item.setdefault("new_code", item.get("title", ""))
                item.setdefault("image_path", "")
                item.setdefault("size", "80x80")
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

    def save_settings(self):
        data = {
            "local_pack": self.local_pack_var.get(),
            "build_provider": self.build_provider_var.get(),
            "preview_provider": self.preview_provider_var.get(),
            "build_libretro_source": self.build_libretro_source_var.get(),
            "preview_libretro_source": self.preview_libretro_source_var.get(),
            "region_order": self.region_order,
            "region_enabled": self.region_enabled,
            "rom_region_enabled": {region: var.get() for region, var in self.rom_region_vars.items()},
            "igdb_client": self.igdb_client_var.get(),
            "igdb_token": self.igdb_token_var.get(),
            "tgdb_key": self.tgdb_key_var.get(),
            "ss_dev_id": self.ss_dev_id_var.get(),
            "ss_dev_pass": self.ss_dev_pass_var.get(),
            "ss_user": self.ss_user_var.get(),
            "ss_pass": self.ss_pass_var.get(),
            "exceptions": [asdict(item) for item in self.exceptions],
            "custom_art": [asdict(item) for item in self.custom_roms],
        }
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.status_var.set("Saved.")


if __name__ == "__main__":
    ThumbnailScraperApp().mainloop()
