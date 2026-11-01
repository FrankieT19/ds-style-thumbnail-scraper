import struct
import tempfile
import unittest
from pathlib import Path

from goomba_save_converter import (
    GoombaSave,
    build_goomba_archive,
    extract_goomba_saves,
    find_matching_rom,
    lzo1x_compress,
    lzo1x_decompress,
    lzo1x_literal_compress,
    merge_goomba_archive,
    rom_checksum,
    scan_gb_rom_index,
)


class GoombaSaveConverterTests(unittest.TestCase):
    def test_literal_lzo_round_trips_across_extension_boundaries(self):
        for size in (4, 238, 239, 273, 274, 528, 8192, 32768):
            with self.subTest(size=size):
                data = bytes((index * 17) & 0xFF for index in range(size))
                self.assertEqual(lzo1x_decompress(lzo1x_literal_compress(data)), data)

    def test_lzo_decodes_short_distance_matches(self):
        m2_stream = b"\x15ABCD\x4c\x00\x11\x00\x00"
        m3_stream = b"\x15ABCD\x21\x0c\x00\x11\x00\x00"

        self.assertEqual(lzo1x_decompress(m2_stream), b"ABCDABC")
        self.assertEqual(lzo1x_decompress(m3_stream), b"ABCDABC")
        repeated = b"ABCDXYZABCDXYZ"
        self.assertEqual(lzo1x_decompress(lzo1x_compress(repeated)), repeated)

    def test_archive_round_trip_preserves_multiple_saves_and_titles(self):
        saves = [
            GoombaSave("TETRIS DX", bytes(range(256)) * 4, 0x12345678),
            GoombaSave("POKEMON CRYSTAL", b"\xA5" * 8192, 0x87654321),
        ]
        archive = build_goomba_archive(saves)

        self.assertEqual(len(archive), 0x10000)
        self.assertEqual(extract_goomba_saves(archive), saves)

    def test_compresses_enough_repetitive_saves_for_one_archive(self):
        saves = [
            GoombaSave(f"GAME {index}", b"\xFF" * 8192, index)
            for index in range(8)
        ]

        archive = build_goomba_archive(saves)

        self.assertEqual(len(extract_goomba_saves(archive)), len(saves))

    def test_merge_replaces_matching_saves_and_preserves_savestates(self):
        existing_saves = [
            GoombaSave("GAME ONE", b"\x11" * 8192, 1),
            GoombaSave("GAME TWO", b"\x22" * 8192, 2),
        ]
        existing = bytearray(build_goomba_archive(existing_saves))
        first_record_size = struct.unpack_from("<H", existing, 4)[0]
        savestate = (
            struct.pack("<HHIII", 52, 0, 4, 0, 0xDEADBEEF)
            + b"GAME ONE".ljust(32, b"\0")
            + b"\0" * 4
        )
        insertion_point = 4 + first_record_size
        existing[insertion_point:insertion_point] = savestate
        existing = existing[:0x10000]

        updated = GoombaSave("GAME ONE", b"\x33" * 8192, 1)
        added = GoombaSave("GAME THREE", b"\x44" * 8192, 3)
        merged = merge_goomba_archive(bytes(existing), [updated, added])

        self.assertIn(savestate, merged)
        self.assertEqual(
            {save.checksum: save for save in extract_goomba_saves(merged)},
            {1: updated, 2: existing_saves[1], 3: added},
        )

    def test_extract_uses_unflushed_sram_when_config_marks_it_active(self):
        save = GoombaSave("TETRIS DX", b"\x11" * 8192, 0x12345678)
        archive = bytearray(build_goomba_archive([save]))
        archive[0xE000:0x10000] = b"\x42" * 8192
        config_offset = 4 + struct.unpack_from("<H", archive, 4)[0]
        struct.pack_into("<I", archive, config_offset + 8, save.checksum)

        self.assertEqual(
            extract_goomba_saves(bytes(archive))[0].data,
            b"\x42" * 8192,
        )
        self.assertEqual(
            extract_goomba_saves(bytes(archive[:0xE200]))[0].data,
            save.data,
        )

    def test_archive_rejects_non_goomba_data(self):
        with self.assertRaisesRegex(ValueError, "recognized"):
            extract_goomba_saves(b"not an ESV archive")

    def test_sav_matching_uses_rom_header_title_and_jagoomba_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom_path = root / "roms" / "Tetris DX (USA).gbc"
            rom_path.parent.mkdir()
            rom = bytearray(0x8000)
            rom[0x134:0x143] = b"TETRIS DX\0\0\0\0\0\0"
            rom_path.write_bytes(rom)
            save_path = root / "SYSTEM" / "SAVER" / "Tetris DX.sav"
            save_path.parent.mkdir(parents=True)
            save_path.write_bytes(b"\0" * 8192)

            title, checksum = find_matching_rom(save_path, root)

            self.assertEqual(title, "TETRIS DX")
            self.assertEqual(checksum, rom_checksum(bytes(rom)))

    def test_sav_matching_rejects_ambiguous_rom_titles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, value in (("one.gb", 1), ("two.gbc", 2)):
                rom = bytearray(0x8000)
                rom[0x134:0x143] = b"SHARED GAME\0\0\0\0"
                rom[0x100] = value
                path = root / name
                path.write_bytes(rom)
            save_path = root / "SHARED GAME.sav"

            with self.assertRaisesRegex(ValueError, "different checksum"):
                find_matching_rom(save_path, root)

    def test_sav_matching_accounts_for_sixteen_character_gb_titles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = bytearray(0x8000)
            rom[0x134:0x143] = b"123456789012345"
            (root / "1234567890123456.gb").write_bytes(rom)
            save_path = root / "1234567890123456.sav"

            title, checksum = find_matching_rom(save_path, root)

            self.assertEqual(title, "123456789012345")
            self.assertEqual(checksum, rom_checksum(bytes(rom)))

    def test_sav_matching_uses_eleven_character_gbc_title_when_header_has_no_terminator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = bytearray(0x8000)
            rom[0x134:0x143] = b"POKEMONCRYSTAL!"
            rom[0x143] = 0x80
            (root / "pokemon-crystal.gbc").write_bytes(rom)
            save_path = root / "POKEMONCRYS.sav"

            title, checksum = find_matching_rom(save_path, root)

            self.assertEqual(title, "POKEMONCRYS")
            self.assertEqual(checksum, rom_checksum(bytes(rom)))

    def test_rom_index_reports_progress_for_valid_and_invalid_rom_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "broken.gb").write_bytes(b"short")
            valid_rom = bytearray(0x8000)
            valid_rom[0x134:0x143] = b"TETRIS DX".ljust(15, b"\0")
            (root / "tetris.gbc").write_bytes(valid_rom)
            progress = []

            index = scan_gb_rom_index(
                root,
                lambda current, total, path: progress.append((current, total, path)),
            )

        self.assertIn("tetrisdx", index)
        self.assertEqual([current for current, _, _ in progress], [0, 1, 2])
        self.assertTrue(all(total == 2 for _, total, _ in progress))

    def test_literal_lzo_rejects_oversized_output(self):
        stream = lzo1x_literal_compress(b"x" * 512)
        with self.assertRaisesRegex(ValueError, "larger than supported"):
            lzo1x_decompress(stream, max_output=256)


if __name__ == "__main__":
    unittest.main()
