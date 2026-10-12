"""Tests for No-Intro filename cleanup and streamed ROM hashes."""
import hashlib
import tempfile
import unittest
import zlib
from pathlib import Path

from rom_matching import compute_rom_hashes, strip_nointro_tags


class RomMatchingUtilityTests(unittest.TestCase):
    def test_preserves_nointro_region_tags_while_stripping_other_metadata(self):
        self.assertEqual(
            strip_nointro_tags("Sonic the Hedgehog (USA, Europe) (Rev 1) (En,Ja) [!] [b1]"),
            "Sonic the Hedgehog (USA, Europe)",
        )
        self.assertEqual(
            strip_nointro_tags("Dragon Warrior (Japan) (Rev A) [!]"),
            "Dragon Warrior (Japan)",
        )

    def test_strips_language_and_status_tags_but_keeps_region_tag(self):
        self.assertEqual(
            strip_nointro_tags("Tetris (USA) (En) (Beta 2) [b1]"),
            "Tetris (USA)",
        )

    def test_preserves_parenthetical_words_that_are_not_known_release_tags(self):
        self.assertEqual(
            strip_nointro_tags("The Legend (The Lost Levels) (USA)"),
            "The Legend (The Lost Levels) (USA)",
        )

    def test_hashes_crc32_md5_sha1_and_size_in_one_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "known.gb"
            path.write_bytes(b"abc")
            result = compute_rom_hashes(path, chunk_size=4096)
        self.assertEqual(result["crc"], f"{zlib.crc32(b'abc') & 0xffffffff:08X}")
        self.assertEqual(result["md5"], hashlib.md5(b"abc").hexdigest())
        self.assertEqual(result["sha1"], hashlib.sha1(b"abc").hexdigest())
        self.assertEqual(result["size"], 3)

    def test_hashing_rejects_an_empty_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.gb"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty ROM"):
                compute_rom_hashes(path)


if __name__ == "__main__":
    unittest.main()
