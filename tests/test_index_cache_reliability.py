"""Offline tests for JSON index cache recovery and network failure handling."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ezflash_gba_full_library import load_gba_library
from ezflash_gba_thumbs import load_libretro_index
from ezflash_gba_pack_converter import ArtFile, choose_preferred_art

APP_PATH = Path(__file__).resolve().parents[1] / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_cache_test", APP_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class IndexCacheReliabilityTests(unittest.TestCase):
    def test_gba_art_region_and_alt_markers_are_case_insensitive(self):
        usa = ArtFile(Path("Tetris (uSa).png"), "Tetris", False)
        europe = ArtFile(Path("Tetris (eUrOpE).png"), "Tetris", True)
        alt = ArtFile(Path("Tetris (aLt).png"), "Tetris", False)
        self.assertEqual(choose_preferred_art([europe, usa]), usa)
        self.assertEqual(choose_preferred_art([usa, alt]), usa)

    def test_main_index_refetches_malformed_cache_and_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "index.json"
            path.write_text("{broken", encoding="utf-8")
            payload = {"tree": [{"path": "Named_Boxarts/Tetris.png"}]}
            with patch.object(APP, "http_get", return_value=json.dumps(payload).encode()) as get:
                self.assertEqual(APP.load_libretro_source_index(path, "Named_Boxarts", "Game Boy"), ["Tetris.png"])
                self.assertEqual(APP.load_libretro_source_index(path, "Named_Boxarts", "Game Boy"), ["Tetris.png"])
            get.assert_called_once()

    def test_invalid_cached_gba_library_refetches_but_network_failure_propagates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "library.json"
            path.write_text("[{}]", encoding="utf-8")
            dat = 'game (\n name "Tetris"\n serial "ATRE"\n)\n'
            with patch("ezflash_gba_full_library.http_get", return_value=dat.encode()) as get:
                self.assertEqual(load_gba_library(path)[0].title, "Tetris")
                self.assertEqual(load_gba_library(path)[0].title, "Tetris")
            get.assert_called_once()
            path.write_text("[]", encoding="utf-8")
            with patch("ezflash_gba_full_library.http_get", side_effect=OSError("offline")):
                with self.assertRaisesRegex(OSError, "offline"):
                    load_gba_library(path)

    def test_standalone_index_refetches_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "index.json"
            path.write_text("null", encoding="utf-8")
            names = [f"Game {index}.png" for index in range(1001)]
            payload = {"tree": [{"path": f"Named_Boxarts/{name}"} for name in names]}
            with patch("ezflash_gba_thumbs.http_get", return_value=json.dumps(payload).encode()) as get:
                self.assertEqual(load_libretro_index(path), sorted(names))
                self.assertEqual(load_libretro_index(path), sorted(names))
            get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
