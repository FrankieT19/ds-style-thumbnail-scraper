"""Read and write Jagoomba/Goomba Color SRAM archives."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


GOOMBA_STATE_IDS = {0x57A731D8, 0x57A731D9}
SRAM_RECORD_TYPE = 1
CONFIG_RECORD_TYPE = 2
HEADER_SIZE = 48
ARCHIVE_SIZE = 0x10000
ARCHIVE_DATA_LIMIT = 0xE000
MAX_SAVE_SIZE = 0x8000
ROM_EXTENSIONS = {".gb", ".gbc"}


@dataclass(frozen=True)
class GoombaSave:
    title: str
    data: bytes
    checksum: int


def _read_byte(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("The LZO stream ended unexpectedly.")
    return data[offset], offset + 1


def lzo1x_decompress(data: bytes, max_output: int = MAX_SAVE_SIZE) -> bytes:
    """Decode one LZO1X stream, rejecting invalid references and oversized output."""
    output = bytearray()
    offset = 0

    def read_extended_length(value: int, base: int) -> int:
        nonlocal offset
        if value:
            return value + base
        while True:
            value, offset = _read_byte(data, offset)
            if value:
                return base + value
            base += 255

    def copy_literals(count: int) -> None:
        nonlocal offset
        if count < 0 or offset + count > len(data):
            raise ValueError("The LZO stream contains a truncated literal run.")
        if len(output) + count > max_output:
            raise ValueError("The decompressed save is larger than supported.")
        output.extend(data[offset:offset + count])
        offset += count

    def copy_match(distance: int, count: int) -> None:
        if distance <= 0 or distance > len(output):
            raise ValueError("The LZO stream contains an invalid back-reference.")
        if len(output) + count > max_output:
            raise ValueError("The decompressed save is larger than supported.")
        start = len(output) - distance
        for index in range(count):
            output.append(output[start + index])

    token, offset = _read_byte(data, offset)
    if token > 17:
        literal_count = token - 17
        copy_literals(literal_count)
        token, offset = _read_byte(data, offset)
        if token < 16:
            raise ValueError("The LZO stream has an invalid initial match.")

    while True:
        if token < 16:
            if token == 0:
                token = read_extended_length(token, 15)
            copy_literals(token + 3)
            token, offset = _read_byte(data, offset)
            if token < 16:
                low, offset = _read_byte(data, offset)
                distance = 0x801 + (token >> 2) + (low << 2)
                copy_match(distance, 3)
                literal_count = data[offset - 2] & 3
                if literal_count:
                    copy_literals(literal_count)
                token, offset = _read_byte(data, offset)
                if literal_count == 0:
                    continue

        while True:
            if token >= 64:
                low, offset = _read_byte(data, offset)
                distance = 1 + ((token >> 2) & 7) + (low << 3)
                match_count = (token >> 5) + 1
            elif token >= 32:
                length = token & 31
                if length == 0:
                    length = read_extended_length(length, 31)
                low, offset = _read_byte(data, offset)
                high, offset = _read_byte(data, offset)
                distance = 1 + (low >> 2) + (high << 6)
                match_count = length + 2
            elif token >= 16:
                distance_base = (token & 8) << 11
                length = token & 7
                if length == 0:
                    length = read_extended_length(length, 7)
                low, offset = _read_byte(data, offset)
                high, offset = _read_byte(data, offset)
                distance = distance_base + (low >> 2) + (high << 6)
                if distance == 0:
                    if any(data[offset:]):
                        raise ValueError("The LZO stream has unexpected data after its end marker.")
                    return bytes(output)
                distance += 0x4000
                match_count = length + 2
            else:
                low, offset = _read_byte(data, offset)
                distance = 1 + (token >> 2) + (low << 2)
                match_count = 2

            copy_match(distance, match_count)
            literal_count = data[offset - 2] & 3
            if literal_count == 0:
                token, offset = _read_byte(data, offset)
                break

            copy_literals(literal_count)
            token, offset = _read_byte(data, offset)
            if token < 16:
                low, offset = _read_byte(data, offset)
                distance = 1 + (token >> 2) + (low << 2)
                copy_match(distance, 3)
                literal_count = data[offset - 2] & 3
                if literal_count:
                    copy_literals(literal_count)
                token, offset = _read_byte(data, offset)
                if literal_count == 0:
                    break


def lzo1x_literal_compress(data: bytes) -> bytes:
    """Encode a valid literal-only LZO1X stream."""
    if not data:
        raise ValueError("Empty save data cannot be encoded as an LZO1X stream.")
    length = len(data)
    if length <= 238:
        prefix = bytes((length + 17,))
    else:
        remainder = length - 18
        prefix_bytes = bytearray((0,))
        while remainder > 255:
            prefix_bytes.append(0)
            remainder -= 255
        prefix_bytes.append(remainder)
        prefix = bytes(prefix_bytes)
    return prefix + data + b"\x11\x00\x00"


def _literal_run_prefix(length: int, initial: bool = False) -> bytes:
    if initial:
        if length <= 238:
            return bytes((length + 17,))
        base = 18
    elif length <= 18:
        return bytes((length - 3,))
    else:
        base = 18

    remainder = length - base
    prefix = bytearray((0,))
    while remainder > 255:
        prefix.append(0)
        remainder -= 255
    prefix.append(remainder)
    return bytes(prefix)


def lzo1x_compress(data: bytes) -> bytes:
    """Encode LZO1X matches for repeated save data, falling back to literals."""
    if not data:
        raise ValueError("Empty save data cannot be encoded as an LZO1X stream.")

    positions: dict[bytes, list[int]] = {}
    output = bytearray()

    def remember(start: int, end: int) -> None:
        for index in range(start, min(end, len(data) - 2)):
            key = data[index:index + 3]
            positions.setdefault(key, []).append(index)

    def find_match(index: int) -> tuple[int, int] | None:
        if index + 3 > len(data):
            return None
        candidates = positions.get(data[index:index + 3], ())
        best_distance = 0
        best_length = 0
        for candidate in reversed(candidates):
            distance = index - candidate
            if distance > 0x4000:
                break
            length = 3
            limit = min(33, len(data) - index)
            while length < limit and data[candidate + length] == data[index + length]:
                length += 1
            if length > best_length:
                best_distance = distance
                best_length = length
                if length == limit:
                    break
        if best_length < 3:
            return None
        return best_distance, best_length

    def find_next_match(start: int) -> tuple[int, tuple[int, int] | None]:
        index = start
        while index + 3 <= len(data):
            match = find_match(index)
            if match:
                return index, match
            remember(index, index + 1)
            index += 1
        return len(data), None

    remember(0, min(4, len(data)))
    first_match_at, first_match = find_next_match(min(4, len(data)))
    if first_match is None:
        return lzo1x_literal_compress(data)

    output.extend(_literal_run_prefix(first_match_at, initial=True))
    output.extend(data[:first_match_at])
    index = first_match_at
    while first_match is not None:
        distance, length = first_match
        if distance <= 2048 and length <= 8:
            distance_code = distance - 1
            command = bytearray((((length - 1) << 5) | ((distance_code & 7) << 2), distance_code >> 3))
            literal_code_offset = 0
        else:
            distance_code = distance - 1
            command = bytearray((32 | (length - 2), (distance_code & 0x3F) << 2, distance_code >> 6))
            literal_code_offset = 1

        match_end = index + length
        remember(index, match_end)
        next_match_at, next_match = find_next_match(match_end)
        trailing = data[match_end:next_match_at]
        if len(trailing) <= 3:
            command[literal_code_offset] |= len(trailing)
            output.extend(command)
            output.extend(trailing)
        else:
            output.extend(command)
            output.extend(_literal_run_prefix(len(trailing)))
            output.extend(trailing)
        index = next_match_at
        first_match = next_match

    output.extend(b"\x11\x00\x00")
    return bytes(output)


def _display_title(raw_title: bytes) -> str:
    return raw_title.split(b"\0", 1)[0].decode("ascii", errors="replace").strip()


def _safe_filename(title: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    return safe or "Game Boy Save"


def _archive_records(data: bytes) -> tuple[int, list[bytes]]:
    if len(data) < 4:
        raise ValueError("The file is too small to be a Jagoomba/Goomba save archive.")
    state_id = struct.unpack_from("<I", data)[0]
    if state_id not in GOOMBA_STATE_IDS:
        raise ValueError("This is not a recognized Jagoomba/Goomba Color save archive.")

    records = []
    offset = 4
    for _ in range(1024):
        if offset + 4 > len(data):
            raise ValueError("The save archive ended before its record terminator.")
        record_size, record_type = struct.unpack_from("<HH", data, offset)
        if record_size == 0:
            break
        if record_size < HEADER_SIZE or record_size % 4 or offset + record_size > len(data):
            raise ValueError("The save archive contains an invalid record size.")
        records.append(data[offset:offset + record_size])
        offset += record_size
    else:
        raise ValueError("The save archive contains too many records.")
    return state_id, records


def parse_goomba_archive(data: bytes, require_saves: bool = True) -> tuple[list[GoombaSave], int | None]:
    """Return all SRAM records and the active, potentially unflushed SRAM checksum."""
    _state_id, records = _archive_records(data)
    saves: list[GoombaSave] = []
    active_checksum: int | None = None
    for record in records:
        record_size, record_type = struct.unpack_from("<HH", record)
        uncompressed_size, _frame_count, checksum = struct.unpack_from("<III", record, 4)
        if record_type == SRAM_RECORD_TYPE:
            if not 0 < uncompressed_size <= MAX_SAVE_SIZE:
                raise ValueError("The archive contains a save with an unsupported size.")
            compressed = record[HEADER_SIZE:]
            payload = lzo1x_decompress(compressed)
            if len(payload) != uncompressed_size:
                raise ValueError("The decompressed save size does not match its archive header.")
            title = _display_title(record[16:48])
            if not title:
                raise ValueError("The archive contains a save without a game title.")
            saves.append(GoombaSave(title, payload, checksum))
        elif record_type == CONFIG_RECORD_TYPE and record_size >= 12:
            active_checksum = struct.unpack_from("<I", record, 8)[0] or None

    if require_saves and not saves:
        raise ValueError("The archive does not contain any Game Boy or Game Boy Color SRAM saves.")
    return saves, active_checksum


def extract_goomba_saves(data: bytes) -> list[GoombaSave]:
    saves, active_checksum = parse_goomba_archive(data, require_saves=False)
    if not saves:
        raise ValueError("The archive does not contain any Game Boy or Game Boy Color SRAM saves.")
    if active_checksum is None or len(data) < ARCHIVE_SIZE:
        return saves

    active_data = data[0xE000:0x10000]
    updated = []
    for save in saves:
        if save.checksum == active_checksum and len(save.data) <= len(active_data):
            updated.append(GoombaSave(save.title, active_data[:len(save.data)], save.checksum))
        else:
            updated.append(save)
    return updated


def build_goomba_archive(saves: list[GoombaSave]) -> bytes:
    """Build a Goomba Color SRAM image with SRAM entries and a clean config record."""
    if not saves:
        raise ValueError("Select at least one .sav file to create an ESV archive.")

    archive = bytearray(struct.pack("<I", 0x57A731D8))
    for save in saves:
        archive.extend(_encode_sram_record(save))

    archive.extend(struct.pack("<HH", HEADER_SIZE, CONFIG_RECORD_TYPE))
    archive.extend(b"\0" * 4)
    archive.extend(struct.pack("<I", 0))
    archive.extend(b"\0" * 4)
    archive.extend(b"CFG".ljust(32, b"\0"))
    archive.extend(b"\0\0\0\0\xff\xff\xff\xff")
    if len(archive) > ARCHIVE_DATA_LIMIT:
        raise ValueError(
            "The selected saves exceed the space available in a Jagoomba/Goomba archive."
        )
    archive.extend(b"\0" * (ARCHIVE_SIZE - len(archive)))
    return bytes(archive)


def _encode_sram_record(save: GoombaSave) -> bytes:
    if not 0 < len(save.data) <= MAX_SAVE_SIZE:
        raise ValueError(f"{save.title}: save size must be between 1 byte and 32 KiB.")
    if not 0 <= save.checksum <= 0xFFFFFFFF:
        raise ValueError(f"{save.title}: ROM checksum is invalid.")
    title = save.title.encode("ascii", errors="replace")[:15]
    compressed = lzo1x_compress(save.data)
    record_size = HEADER_SIZE + len(compressed)
    padding = (-record_size) % 4
    record_size += padding
    return (
        struct.pack("<HHIII", record_size, SRAM_RECORD_TYPE, len(save.data), 0, save.checksum)
        + title.ljust(32, b"\0")
        + compressed
        + b"\0" * padding
    )


def merge_goomba_archive(data: bytes, incoming_saves: list[GoombaSave]) -> bytes:
    """Add or replace SRAM records while preserving savestates and other archive records."""
    if not incoming_saves:
        raise ValueError("Select at least one .sav file to add to the ESV archive.")
    state_id, records = _archive_records(data)
    old_saves = extract_goomba_saves(data) if any(
        struct.unpack_from("<HH", record)[1] == SRAM_RECORD_TYPE for record in records
    ) else []
    merged_saves = {save.checksum: save for save in old_saves}
    for save in incoming_saves:
        merged_saves[save.checksum] = save

    encoded_saves = {
        checksum: _encode_sram_record(save)
        for checksum, save in merged_saves.items()
    }
    used_checksums: set[int] = set()
    merged_records = []
    config_found = False
    for record in records:
        record_size, record_type = struct.unpack_from("<HH", record)
        if record_type == SRAM_RECORD_TYPE:
            checksum = struct.unpack_from("<I", record, 12)[0]
            if checksum not in used_checksums:
                merged_records.append(encoded_saves[checksum])
                used_checksums.add(checksum)
        elif record_type == CONFIG_RECORD_TYPE:
            config_found = True
            if record_size >= 12:
                record = record[:8] + b"\0\0\0\0" + record[12:]
            merged_records.append(record)
        else:
            merged_records.append(record)

    for checksum, record in encoded_saves.items():
        if checksum not in used_checksums:
            merged_records.append(record)
    if not config_found:
        config_record = (
            struct.pack("<HH", HEADER_SIZE, CONFIG_RECORD_TYPE)
            + b"\0" * 4
            + struct.pack("<I", 0)
            + b"\0" * 4
            + b"CFG".ljust(32, b"\0")
        )
        merged_records.append(config_record)

    archive = bytearray(struct.pack("<I", state_id))
    for record in merged_records:
        archive.extend(record)
    archive.extend(b"\0\0\0\0\xff\xff\xff\xff")
    if len(archive) > ARCHIVE_DATA_LIMIT:
        raise ValueError("The combined saves exceed the space available in the ESV archive.")
    archive.extend(b"\0" * (ARCHIVE_SIZE - len(archive)))
    return bytes(archive)


def rom_checksum(rom: bytes) -> int:
    """Calculate Jagoomba Color's checksum for an ordinary, untrimmed GB/GBC ROM."""
    if len(rom) < 0x4000:
        raise ValueError("The matching GB/GBC ROM is smaller than 16 KiB.")
    return sum(
        int.from_bytes(rom[offset:offset + 4], "little")
        for offset in range(0, 0x4000, 128)
    ) & 0xFFFFFFFF


def rom_title(rom: bytes) -> str:
    if len(rom) < 0x144:
        raise ValueError("The GB/GBC ROM header is incomplete.")
    title = bytearray(rom[0x134:0x143])
    if rom[0x143] >= 0x80 and all(title[11:15]):
        title[11:15] = b"\0" * 4
    return _display_title(bytes(title))


def _normalized_title(title: str) -> str:
    title = re.sub(r"\s*[\[(][^)\]]*[\])]\s*$", "", title)
    return re.sub(r"[^a-z0-9]", "", title.casefold())


def scan_gb_rom_index(
    root: Path,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> dict[str, dict[int, str]]:
    """Index GB/GBC ROM checksums by normalized cartridge title."""
    index: dict[str, dict[int, str]] = {}
    try:
        rom_paths = sorted(
            (path for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in ROM_EXTENSIONS),
            key=lambda path: str(path).casefold(),
        )
    except OSError as exc:
        raise ValueError(f"Could not scan the SD card for GB/GBC ROMs: {exc}") from exc

    if progress_callback is not None:
        progress_callback(0, len(rom_paths), root)
    for current, rom_path in enumerate(rom_paths, start=1):
        try:
            rom = rom_path.read_bytes()
            title = rom_title(rom)
            checksum = rom_checksum(rom)
        except (OSError, ValueError):
            if progress_callback is not None:
                progress_callback(current, len(rom_paths), rom_path)
            continue
        key = _normalized_title(title)
        if key:
            index.setdefault(key, {})[checksum] = title
        filename_key = _normalized_title(rom_path.stem)
        if filename_key:
            index.setdefault(filename_key, {})[checksum] = title
        if progress_callback is not None:
            progress_callback(current, len(rom_paths), rom_path)
    return index


def match_save_to_rom(save_path: Path, rom_index: dict[str, dict[int, str]]) -> tuple[str, int]:
    """Find the unique GB/GBC ROM checksum matching a .sav filename."""
    save_title = _normalized_title(save_path.stem)
    matches = rom_index.get(save_title)
    if matches is None:
        matches = rom_index.get(_normalized_title(save_path.stem[:15]), {})
    if not matches:
        raise ValueError(f"No matching GB/GBC ROM was found for {save_path.name}.")
    if len(matches) > 1:
        raise ValueError(f"More than one ROM with a different checksum matches {save_path.name}.")
    checksum, title = next(iter(matches.items()))
    return title, checksum


def find_matching_rom(save_path: Path, root: Path) -> tuple[str, int]:
    """Find a GB/GBC ROM whose header title matches a .sav filename."""
    return match_save_to_rom(save_path, scan_gb_rom_index(root))


def save_filename(title: str) -> str:
    return _safe_filename(title) + ".sav"
