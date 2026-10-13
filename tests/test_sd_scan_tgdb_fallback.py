"""SD scan tests for automatic TheGamesDB fallback on Libretro misses."""

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
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_sd_tgdb_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)


def png_bytes(size=(30, 40)):
    stream = io.BytesIO()
    Image.new("RGB", size, (30, 110, 190)).save(stream, format="PNG")
    return stream.getvalue()


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class Status:
    def set(self, _value):
        pass


class FallbackProviders:
    def __init__(self, result=None):
        self.result = result
        self.fallback_calls = []

    def find_libretro_art_name(self, query, system, folder):
        return None

    def search_thegamesdb_many(self, query, max_results=1, system=APP_MODULE.DEFAULT_SYSTEM):
        self.fallback_calls.append((query, max_results, system))
        if self.result is None:
            raise LookupError("No TheGamesDB match")
        return [self.result]


def setup_app(base_dir: Path, providers, api_key="test-api-key"):
    app = object.__new__(APP_MODULE.ThumbnailScraperApp)
    app.base_dir = base_dir
    app.custom_roms = []
    app.providers = providers
    app.after = lambda _delay, callback: callback()
    app.status_var = Status()
    app.tgdb_key_var = Value(api_key)
    app.ask_sd_download_retry_skip = lambda *_args: "skip"
    return app


def make_rom(root: Path, name="Tetris") -> Path:
    rom = root / "Game Boy" / "T" / f"{name}.gb"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.touch()
    return rom


class SdScanTheGamesDbFallbackTests(unittest.TestCase):
    def test_sd_scan_uses_tgdb_when_libretro_has_no_match(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "sd"
            make_rom(root)
            result = APP_MODULE.ProviderResult("TheGamesDB", "Tetris - front.png", png_bytes(), "Game Boy")
            providers = FallbackProviders(result)
            app = setup_app(base / "app", providers)

            scan = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(scan["matched_files"], 1)
            self.assertEqual(len(scan["additions"]), 1)
            self.assertEqual(scan["unmatched"], [])
            self.assertEqual(providers.fallback_calls, [("Tetris", 1, "Game Boy")])
            self.assertTrue(Path(scan["additions"][0].image_path).is_file())

    def test_sd_scan_does_not_query_tgdb_when_output_already_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "sd"
            make_rom(root)
            existing = root / "SYSTEM" / "IMGS2" / "Game Boy" / "T" / "Tetris.bmp"
            existing.parent.mkdir(parents=True)
            Image.new("RGB", (80, 80), (20, 30, 40)).save(existing, format="BMP")
            providers = FallbackProviders()
            app = setup_app(base / "app", providers)

            scan = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(providers.fallback_calls, [])
            self.assertEqual(scan["additions"], [])
            self.assertEqual(scan["skipped_existing"], 1)
            self.assertEqual(scan["unmatched"], [])

    def test_sd_scan_reports_need_for_api_key_if_libretro_misses(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "sd"
            make_rom(root)
            providers = FallbackProviders()
            app = setup_app(base / "app", providers, api_key="")

            scan = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(providers.fallback_calls, [])
            self.assertEqual(len(scan["unmatched"]), 1)
            self.assertIn("add a TheGamesDB API key", scan["unmatched"][0])


if __name__ == "__main__":
    unittest.main()
