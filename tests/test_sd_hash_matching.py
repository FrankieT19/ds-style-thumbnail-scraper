"""Tests the opt-in SD hash lookup path and No-Intro query cleanup."""
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_sd_hash_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)


class FakeStatus:
    def set(self, _value):
        pass


class FakeProviders:
    def __init__(self, match_by_hash=None):
        self.query_names = []
        self.hash_calls = []
        self.match_by_hash = match_by_hash

    def find_libretro_art_name(self, query, system, folder):
        self.query_names.append((query, system, folder))
        return None

    def search_fallback_many(self, query, max_results=1, system=APP_MODULE.DEFAULT_SYSTEM,
                             after_provider="Libretro", prior_errors=None):
        self.query_names.append((query, system, "name-fallback"))
        raise LookupError("all name-based providers missed")

    def search_hash_fallback(self, path, query, system=APP_MODULE.DEFAULT_SYSTEM):
        self.hash_calls.append((Path(path), query, system))
        if self.match_by_hash is None:
            raise LookupError("hash providers missed")
        return [self.match_by_hash]


def png_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (30, 40), (35, 85, 125)).save(stream, format="PNG")
    return stream.getvalue()


def make_rom(root: Path, filename: str) -> Path:
    path = root / "Game Boy" / filename[0].upper() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"sample ROM bytes for hashing")
    return path


def make_app(base_dir: Path, match_by_hash=None):
    app = object.__new__(APP_MODULE.ThumbnailScraperApp)
    app.base_dir = base_dir
    app.custom_roms = []
    app.providers = FakeProviders(match_by_hash)
    app.after = lambda _delay, callback: callback()
    app.status_var = FakeStatus()
    app.ask_sd_download_fallback_skip = lambda *_args: "skip"
    return app


class SdHashMatchingTests(unittest.TestCase):
    def test_hashing_is_not_used_when_toggle_is_off(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            rom = make_rom(root, "Tetris (USA) (Rev 1) [!].gb")
            app = make_app(Path(temp) / "app")
            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False, use_hash_matching=False)

            self.assertEqual(app.providers.hash_calls, [])
            self.assertEqual(app.providers.query_names[0][0], "Tetris (USA)")
            self.assertEqual(app.providers.query_names[1][0], "Tetris (USA)")
            self.assertEqual(result["additions"], [])
            self.assertEqual(len(result["unmatched"]), 1)
            self.assertTrue(rom.is_file())

    def test_hashing_is_attempted_only_after_name_providers_miss(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            rom = make_rom(root, "Tetris (USA) (Rev 1) [!].gb")
            expected = APP_MODULE.ProviderResult(
                "ScreenScraper", "Tetris - box-2D [ROM hash match]", png_bytes(), "Game Boy"
            )
            app = make_app(Path(temp) / "app", expected)

            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False, use_hash_matching=True)

            self.assertEqual([query[0] for query in app.providers.query_names], ["Tetris (USA)", "Tetris (USA)"])
            self.assertEqual(app.providers.hash_calls, [(rom, "Tetris (USA)", "Game Boy")])
            self.assertEqual(result["matched_files"], 1)
            self.assertEqual(len(result["additions"]), 1)
            self.assertEqual(result["additions"][0].system, "Game Boy")
            self.assertTrue(Path(result["additions"][0].image_path).is_file())

    def test_hash_miss_is_reported_without_aborting_the_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Unknown Game (Europe).gb")
            app = make_app(Path(temp) / "app")

            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False, use_hash_matching=True)

            self.assertEqual(result["additions"], [])
            self.assertEqual(len(result["unmatched"]), 1)
            self.assertIn("hash search", result["unmatched"][0])
            self.assertEqual(len(app.providers.hash_calls), 1)


if __name__ == "__main__":
    unittest.main()
