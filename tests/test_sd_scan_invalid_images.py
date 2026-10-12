"""Regression tests for invalid SD-scan downloads, user retry/skip, and caching."""

import importlib.util
import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_scan_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)


class FakeProviders:
    def find_libretro_art_name(self, query, system, folder):
        return f"{query}.png"


class FakeStatus:
    def set(self, _value):
        pass


def png_bytes(size=(120, 80)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, (20, 80, 120)).save(stream, format="PNG")
    return stream.getvalue()


def make_app(base_dir: Path, choices=None):
    app = object.__new__(APP_MODULE.ThumbnailScraperApp)
    app.base_dir = base_dir
    app.custom_roms = []
    app.providers = FakeProviders()
    app.after = lambda _delay, callback: callback()
    app.status_var = FakeStatus()
    choices = list(choices or [])
    prompt_calls = []

    def choose(system, art_name, error):
        prompt_calls.append((system, art_name, str(error)))
        return choices.pop(0) if choices else "skip"

    app.ask_sd_download_retry_skip = choose
    return app, prompt_calls


def make_rom(root: Path, name="Good Game") -> Path:
    rom = root / "Game Boy" / name[0] / f"{name}.gb"
    rom.parent.mkdir(parents=True, exist_ok=True)
    rom.touch()
    return rom


class SdScanInvalidImageTests(unittest.TestCase):
    def with_mock_downloads(self, fake):
        original_http_get = APP_MODULE.http_get
        original_raw_url = APP_MODULE.libretro_raw_url
        APP_MODULE.http_get = fake
        APP_MODULE.libretro_raw_url = lambda system, folder, name: f"https://example.invalid/{name}"
        self.addCleanup(setattr, APP_MODULE, "http_get", original_http_get)
        self.addCleanup(setattr, APP_MODULE, "libretro_raw_url", original_raw_url)

    def test_invalid_remote_payload_can_be_skipped_and_other_games_continue(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            if "/Bad Game.png" in url:
                return b"<html><body>temporary upstream error</body></html>"
            return png_bytes()

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            cache_dir = Path(temp) / "app"
            make_rom(root, "Bad Game")
            make_rom(root, "Good Game")
            app, prompts = make_app(cache_dir, ["skip"])

            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(result["files"], 2)
            self.assertEqual(result["matched_files"], 2)
            self.assertEqual(len(result["additions"]), 1)
            self.assertEqual(len(result["download_errors"]), 1)
            self.assertIn("skipped after download error", result["download_errors"][0])
            self.assertEqual(len(prompts), 1)
            self.assertEqual(Path(result["additions"][0].image_path).suffix, ".png")

    def test_retry_download_retries_invalid_payload_and_succeeds(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            if len(calls) == 1:
                return b"<html>temporary error</html>"
            return png_bytes()

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Retry Game")
            app, prompts = make_app(Path(temp) / "app", ["retry"])

            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(len(calls), 2)
            self.assertEqual(len(prompts), 1)
            self.assertEqual(len(result["download_errors"]), 0)
            self.assertEqual(len(result["additions"]), 1)
            self.assertTrue(Path(result["additions"][0].image_path).is_file())

    def test_second_scan_reuses_persistent_art_cache_without_network(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            return png_bytes()

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Cached Game")
            app, _prompts = make_app(Path(temp) / "app")

            first = app._scan_sd_worker(root, "Box Art", ["80x80"], False)
            self.assertEqual(len(first["additions"]), 1)
            self.assertEqual(len(calls), 1)
            first_cache_path = Path(first["additions"][0].image_path)
            self.assertTrue(first_cache_path.is_file())

            # A subsequent scan with an empty custom list still reuses the keyed
            # source cache rather than redownloading the same Libretro image.
            second = app._scan_sd_worker(root, "Box Art", ["80x80"], False)
            self.assertEqual(len(calls), 1)
            self.assertEqual(second["cache_hits"], 1)
            self.assertEqual(len(second["additions"]), 1)
            self.assertEqual(Path(second["additions"][0].image_path), first_cache_path)

    def test_existing_sd_imgs2_thumbnail_is_skipped_without_download(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            return png_bytes()

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Already There")
            existing = root / "SYSTEM" / "IMGS2" / "Game Boy" / "A" / "Already There.bmp"
            existing.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (80, 80), (40, 90, 120)).save(existing, format="BMP")

            app, prompts = make_app(Path(temp) / "app")
            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(calls, [])
            self.assertEqual(prompts, [])
            self.assertEqual(result["skipped_existing"], 1)
            self.assertEqual(result["additions"], [])

    def test_legacy_custom_art_cache_is_reused_for_a_new_size(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            raise AssertionError("A valid image already cached in settings should be reused")

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            rom = make_rom(root, "Legacy Cached Game")
            app_dir = Path(temp) / "app"
            old_cache = Path(temp) / "matched artwork" / "old-hash.png"
            old_cache.parent.mkdir(parents=True, exist_ok=True)
            old_cache.write_bytes(png_bytes())
            app, prompts = make_app(app_dir)
            relative = "Game Boy/L/Legacy Cached Game.gb"
            app.custom_roms = [
                APP_MODULE.CustomRomItem(
                    str(rom),
                    "Legacy Cached Game",
                    "----",
                    "Legacy Cached Game",
                    image_path=str(old_cache),
                    size="80x80",
                    system="Game Boy",
                    rom_relative_path=relative,
                )
            ]

            result = app._scan_sd_worker(root, "Box Art", ["120x80"], False)

            self.assertEqual(calls, [])
            self.assertEqual(prompts, [])
            self.assertEqual(result["cache_hits"], 1)
            self.assertEqual(len(result["additions"]), 1)
            self.assertTrue(Path(result["additions"][0].image_path).is_file())

    def test_previous_generated_imgs_folder_is_recognized(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            return png_bytes()

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Earlier Build Game")
            app_dir = Path(temp) / "app"
            old_output = app_dir / APP_MODULE.OUTPUT_FOLDER_NAME / "2026-10-10_12-00-00" / "IMGS"
            existing = old_output / "Game Boy" / "E" / "Earlier Build Game.bmp"
            existing.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (120, 80), (60, 100, 120)).save(existing, format="BMP")

            app, prompts = make_app(app_dir)
            result = app._scan_sd_worker(root, "Box Art", ["120x80"], False)

            self.assertEqual(calls, [])
            self.assertEqual(prompts, [])
            self.assertEqual(result["skipped_existing"], 1)
            self.assertEqual(result["additions"], [])

    def test_corrupt_existing_sd_thumbnail_is_not_mistaken_for_complete_output(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            return png_bytes()

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Corrupt Output")
            existing = root / "SYSTEM" / "IMGS2" / "Game Boy" / "C" / "Corrupt Output.bmp"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_bytes(b"not a bmp")

            app, _prompts = make_app(Path(temp) / "app")
            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(len(calls), 1)
            self.assertEqual(result["skipped_existing"], 0)
            self.assertEqual(len(result["additions"]), 1)


if __name__ == "__main__":
    unittest.main()
