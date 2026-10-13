"""Utilities for conservative No-Intro title cleanup and ROM checksum lookup."""
from __future__ import annotations

import hashlib
import re
import zlib
from pathlib import Path
from typing import BinaryIO

# No-Intro uses parentheses for release metadata and square brackets for dump
# status/quality tags. Only known metadata in parentheses is removed so a
# legitimate title such as "The Legend (The Lost Levels)" stays intact.
REGION_TAGS = {
    "usa", "us", "u", "europe", "e", "eu", "japan", "j", "world", "w",
    "australia", "australasia", "brazil", "canada", "china", "france",
    "germany", "hong kong", "italy", "korea", "netherlands", "spain",
    "sweden", "taiwan", "asia", "russia", "scandinavia", "united kingdom",
    "uk", "unknown", "international", "pal", "ntsc",
}
LANGUAGE_TAGS = {
    "en", "ja", "fr", "de", "es", "it", "nl", "pt", "sv", "no", "da",
    "fi", "zh", "ko", "pl", "ru", "el", "he", "ar", "tr", "cs", "hu",
    "th", "vi", "id", "ms", "ca", "eu", "hr", "sk", "sl", "ro", "bg",
}
STATUS_TAGS = {
    "beta", "proto", "prototype", "demo", "sample", "unl", "unlicensed",
    "alt", "virtual console", "not for resale", "nfr", "bios", "hack",
    "overdump", "bad dump", "rev a", "rev b", "rev c", "rev 0", "rev 1",
    "rev 2", "rev 3", "rev 4", "revision 1", "revision 2", "revision 3",
    "sgb enhanced", "gb compatible", "rumble version", "enhanced",
}


def _is_region_tag(content: str) -> bool:
    """Return whether a parenthetical tag identifies one or more regions."""
    value = re.sub(r"\s+", " ", content.strip().casefold())
    if value in REGION_TAGS:
        return True
    parts = [re.sub(r"\s+", " ", part.strip().casefold()) for part in value.split(",")]
    return len(parts) > 1 and all(part in REGION_TAGS for part in parts)


def _is_release_tag(content: str) -> bool:
    value = re.sub(r"\s+", " ", content.strip().casefold())
    if not value:
        return False
    if value in REGION_TAGS or value in STATUS_TAGS:
        return True
    # Multi-language and mixed region/language lists such as "En,Ja".
    parts = [re.sub(r"\s+", " ", part.strip().casefold()) for part in value.split(",")]
    if len(parts) > 1 and all(part in REGION_TAGS or part in LANGUAGE_TAGS for part in parts):
        return True
    if value in LANGUAGE_TAGS:
        return True
    # Version / revision designators: (Rev A), (Revision 2), (v1.1), (Version 1.0).
    if re.fullmatch(r"(?:rev(?:ision)?\s*[a-z0-9]+|v\s*\d+(?:[._-]\d+)*|version\s*\d+(?:[._-]\d+)*)", value):
        return True
    # Common No-Intro status variants (Beta 2), (Proto 1), (Hack 3).
    if re.fullmatch(r"(?:beta|proto(?:type)?|sample|demo|hack|alt)\s*\d*", value):
        return True
    return False


def strip_nointro_tags(title: str) -> str:
    """Return a search title with region tags preserved and other metadata cleaned.

    Parenthetical region tags such as (USA), (Europe), (Japan), and (USA, Europe)
    are retained to keep region-specific provider matches possible. Language,
    revision/version, status, and square-bracketed dump tags are stripped. The
    original ROM filename, output path, and cache identity are never changed.
    """
    result = str(title or "").strip()
    # Filename-only, square-bracketed dump flags: [!], [b1], [h], [T+Eng], etc.
    result = re.sub(r"\s*\[[^\]]*\]\s*", " ", result)

    def remove_known_parenthetical(match: re.Match[str]) -> str:
        content = match.group(1)
        if _is_region_tag(content):
            return match.group(0)
        return " " if _is_release_tag(content) else match.group(0)

    result = re.sub(r"\(([^()]*)\)", remove_known_parenthetical, result)
    result = result.replace("_", " ")
    result = re.sub(r"\s+", " ", result).strip(" \t-_,;")
    return result or str(title or "").strip()


def compute_rom_hashes(path: str | Path, chunk_size: int = 1024 * 1024) -> dict[str, str | int]:
    """Stream a ROM file once and return CRC32, MD5, SHA-1 and byte length.

    Call this only after name-based lookup fails; reading the full file is
    intentionally opt-in because large libraries can take time to hash.
    """
    rom_path = Path(path)
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    crc32 = 0
    size = 0
    with rom_path.open("rb") as stream:
        while True:
            block = stream.read(max(4096, int(chunk_size)))
            if not block:
                break
            size += len(block)
            crc32 = zlib.crc32(block, crc32)
            md5.update(block)
            sha1.update(block)
    if size <= 0:
        raise ValueError(f"Cannot hash an empty ROM file: {rom_path.name}")
    return {
        "crc": f"{crc32 & 0xFFFFFFFF:08X}",
        "md5": md5.hexdigest().lower(),
        "sha1": sha1.hexdigest().lower(),
        "size": size,
    }
