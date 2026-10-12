"""Regression tests for invalid SD-scan downloads, fallback/skip, and caching."""

import importlib.util
import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

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

    def search_fallback_many(self, query, max_results=1, system=APP_MODULE.DEFAULT_SYSTEM,
                             after_provider="Libretro", prior_errors=None):
        raise LookupError(f"No fallback configured for {query} on {system}")


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

    app.ask_sd_download_fallback_skip = choose
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

    def test_try_fallback_uses_next_provider_instead_of_retrying_libretro(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            return b"<html>temporary error</html>"

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Retry Game")
            app, prompts = make_app(Path(temp) / "app", ["fallback"])
            fallback_result = APP_MODULE.ProviderResult(
                "TheGamesDB", "Retry Game - front.png", png_bytes(), "Game Boy"
            )
            app.providers.search_fallback_many = Mock(return_value=[fallback_result])

            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            self.assertEqual(len(calls), 1)
            self.assertEqual(len(prompts), 1)
            self.assertEqual(len(result["download_errors"]), 0)
            self.assertEqual(len(result["additions"]), 1)
            self.assertTrue(Path(result["additions"][0].image_path).is_file())
            app.providers.search_fallback_many.assert_called_once_with(
                "Retry Game", max_results=1, system="Game Boy", after_provider="Libretro",
                prior_errors=["Libretro image download: Provider returned invalid or incomplete image data"],
            )

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
            app.providers.find_libretro_art_name = Mock(
                side_effect=AssertionError("Existing output should skip all provider matching")
            )
            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            app.providers.find_libretro_art_name.assert_not_called()
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

    def test_per_rom_cache_is_checked_before_libretro_or_fallback_search(self):
        calls = []

        def fake_http_get(url):
            calls.append(url)
            raise AssertionError("Cached artwork should prevent an online image request")

        self.with_mock_downloads(fake_http_get)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Cached First Game")
            app_dir = Path(temp) / "app"
            app, prompts = make_app(app_dir)
            relative = "Game Boy/C/Cached First Game.gb"
            cache_path = app.sd_scan_rom_cache_path(
                "Named_Boxarts", "Game Boy", relative
            )
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(png_bytes())
            app.providers.find_libretro_art_name = Mock(
                side_effect=AssertionError("Libretro lookup should happen only after cache misses")
            )
            app.providers.search_fallback_many = Mock(
                side_effect=AssertionError("Fallback lookup should happen only after cache misses")
            )

            result = app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            app.providers.find_libretro_art_name.assert_not_called()
            app.providers.search_fallback_many.assert_not_called()
            self.assertEqual(calls, [])
            self.assertEqual(prompts, [])
            self.assertEqual(result["cache_hits"], 1)
            self.assertEqual(len(result["additions"]), 1)
            self.assertEqual(Path(result["additions"][0].image_path), cache_path)

    def test_cached_fallback_art_is_reused_before_retrying_online_providers(self):
        self.with_mock_downloads(lambda _url: (_ for _ in ()).throw(
            AssertionError("Fallback result already contains image bytes")
        ))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "sd"
            make_rom(root, "Fallback Cached Game")
            app_dir = Path(temp) / "app"
            first_app, _prompts = make_app(app_dir)
            first_app.providers.find_libretro_art_name = Mock(return_value=None)
            fallback_result = APP_MODULE.ProviderResult(
                "TheGamesDB", "Fallback Cached Game - front.png", png_bytes(), "Game Boy"
            )
            first_app.providers.search_fallback_many = Mock(return_value=[fallback_result])

            first = first_app._scan_sd_worker(root, "Box Art", ["80x80"], False)
            self.assertEqual(len(first["additions"]), 1)
            first_app.providers.search_fallback_many.assert_called_once()

            second_app, prompts = make_app(app_dir)
            second_app.providers.find_libretro_art_name = Mock(
                side_effect=AssertionError("A valid per-ROM cache should skip Libretro lookup")
            )
            second_app.providers.search_fallback_many = Mock(
                side_effect=AssertionError("A valid per-ROM cache should skip fallback providers")
            )
            second = second_app._scan_sd_worker(root, "Box Art", ["80x80"], False)

            second_app.providers.find_libretro_art_name.assert_not_called()
            second_app.providers.search_fallback_many.assert_not_called()
            self.assertEqual(prompts, [])
            self.assertEqual(second["cache_hits"], 1)
            self.assertEqual(len(second["additions"]), 1)
            self.assertEqual(
                Path(second["additions"][0].image_path),
                Path(first["additions"][0].image_path),
            )

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
