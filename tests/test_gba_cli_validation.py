"""Offline regression tests for standalone GBA utility inputs."""

import tempfile
import unittest
from pathlib import Path

from ezflash_gba_full_library import build_parser as build_full_library_parser
from ezflash_gba_pack_converter import build_parser as build_pack_converter_parser
from ezflash_gba_thumbs import build_parser as build_thumbs_parser, iter_gba_files


class GbaCliValidationTests(unittest.TestCase):
    def test_recursive_scan_finds_mixed_case_gba_extensions_deterministically(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            upper = root / "a" / "FIRST.GBA"
            lower = root / "b" / "second.gba"
            ignored = root / "c" / "not-a-rom.gb"
            for path in (upper, lower, ignored):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

            self.assertEqual(list(iter_gba_files([root])), [upper, lower])

    def test_thumb_dimensions_reject_negative_width_and_nonpositive_height(self):
        parser = build_thumbs_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--width", "-1"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--height", "0"])
        self.assertEqual(parser.parse_args(["--width", "0"]).width, 0)

    def test_pack_converter_requires_positive_dimensions(self):
        parser = build_pack_converter_parser()
        for args in (("--width", "0"), ("--height", "-2")):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                parser.parse_args(list(args))

    def test_full_library_requires_positive_dimensions_and_nonnegative_limit(self):
        parser = build_full_library_parser()
        for args in (("--width", "0"), ("--height", "-2"), ("--limit", "-1")):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                parser.parse_args(list(args))
        self.assertEqual(parser.parse_args(["--limit", "0"]).limit, 0)


if __name__ == "__main__":
    unittest.main()
