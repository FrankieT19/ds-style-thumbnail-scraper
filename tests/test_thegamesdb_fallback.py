"""Offline regression tests for automatic TheGamesDB fallback and API parsing."""

import importlib.util
import io
import tempfile
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_tgdb_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)


def png_bytes(size=(24, 32)):
    stream = io.BytesIO()
    Image.new("RGB", size, (35, 80, 130)).save(stream, format="PNG")
    return stream.getvalue()


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class TheGamesDbFallbackTests(unittest.TestCase):
    def test_libretro_provider_automatically_falls_back_on_no_match(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(
                base_dir=Path(temp),
                tgdb_key_var=Value("test-key"),
            )
            providers = APP_MODULE.Providers(app)
            providers.search_libretro_many = Mock(side_effect=LookupError("no Libretro match"))
            expected = APP_MODULE.ProviderResult("TheGamesDB", "Tetris - front.png", png_bytes(), "Game Boy")
            providers.search_thegamesdb_many = Mock(return_value=[expected])

            result = providers.search_many("Libretro", "Tetris", max_results=1, system="Game Boy")

            self.assertEqual(result, [expected])
            providers.search_libretro_many.assert_called_once_with("Tetris", 1, None, "Game Boy")
            providers.search_thegamesdb_many.assert_called_once_with("Tetris", 1, system="Game Boy")

    def test_invalid_libretro_image_triggers_thegamesdb_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp), tgdb_key_var=Value("test-key"))
            providers = APP_MODULE.Providers(app)
            providers.search_libretro_many = Mock(
                return_value=[APP_MODULE.ProviderResult("Libretro", "Tetris.png", b"not an image", "Game Boy")]
            )
            expected = APP_MODULE.ProviderResult("TheGamesDB", "Tetris - front.png", png_bytes(), "Game Boy")
            providers.search_thegamesdb_many = Mock(return_value=[expected])

            result = providers.search_many("Libretro", "Tetris", max_results=1, system="Game Boy")

            self.assertEqual(result, [expected])
            providers.search_thegamesdb_many.assert_called_once_with("Tetris", 1, system="Game Boy")

    def test_libretro_success_does_not_call_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp), tgdb_key_var=Value("test-key"))
            providers = APP_MODULE.Providers(app)
            expected = APP_MODULE.ProviderResult("Libretro", "Tetris.png", png_bytes(), "Game Boy")
            providers.search_libretro_many = Mock(return_value=[expected])
            providers.search_thegamesdb_many = Mock(side_effect=AssertionError("fallback should not run"))
            self.assertEqual(
                providers.search_many("Libretro", "Tetris", max_results=1, system="Game Boy"),
                [expected],
            )
            providers.search_thegamesdb_many.assert_not_called()

    def test_tgdb_search_uses_system_platform_filter_and_front_boxart(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp), tgdb_key_var=Value("test-key"))
            providers = APP_MODULE.Providers(app)
            image = png_bytes()
            urls = []

            def fake_request_json(url, _headers=None):
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if parsed.path == "/v1/Platforms":
                    return {"data": {"platforms": {"42": {"id": 42, "name": "Nintendo Game Boy"}}}}
                if parsed.path == "/v1.1/Games/ByGameName":
                    self.assertEqual(params["name"], ["Tetris"])
                    self.assertEqual(params["filter[platform]"], ["42"])
                    return {
                        "data": {"games": [{"id": 7, "game_title": "Tetris", "platform": 42}]},
                        "include": {
                            "boxart": {
                                "base_url": {"original": "https://cdn.example/images/original/"},
                                "data": {
                                    "7": [
                                        {"filename": "back/7.png", "side": "back"},
                                        {"filename": "front/7.png", "side": "front"},
                                    ]
                                },
                            }
                        },
                    }
                self.fail(f"Unexpected API URL: {url}")

            def fake_fetch(url, _headers=None):
                urls.append(url)
                return image

            with patch.object(APP_MODULE, "request_json", side_effect=fake_request_json), patch.object(
                APP_MODULE, "fetch_bytes", side_effect=fake_fetch
            ):
                results = providers.search_thegamesdb_many("Tetris", max_results=1, system="Game Boy")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].provider, "TheGamesDB")
            self.assertEqual(results[0].system, "Game Boy")
            self.assertTrue(results[0].label.endswith("7.png"))
            self.assertEqual(urls, ["https://cdn.example/images/original/front/7.png"])

    def test_thegamesdb_absolute_path_filename_is_resolved_without_duplicate_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp), tgdb_key_var=Value("test-key"))
            providers = APP_MODULE.Providers(app)
            image = png_bytes()
            urls = []

            def fake_request_json(url, _headers=None):
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if parsed.path == "/v1/Platforms":
                    return {"data": {"platforms": {"42": {"id": 42, "name": "Nintendo Game Boy"}}}}
                if parsed.path == "/v1.1/Games/ByGameName":
                    return {
                        "data": {"games": [{"id": 7, "game_title": "Tetris", "platform": 42}]},
                        "include": {
                            "boxart": {
                                "base_url": {"original": "https://cdn.example/images/original/"},
                                "data": {"7": [{"filename": "/images/original/boxart/front/7.png", "side": "front"}]},
                            }
                        },
                    }
                self.fail(f"Unexpected API URL: {url}")

            def fake_fetch(url, _headers=None):
                urls.append(url)
                return image

            with patch.object(APP_MODULE, "request_json", side_effect=fake_request_json), patch.object(
                APP_MODULE, "fetch_bytes", side_effect=fake_fetch
            ):
                results = providers.search_thegamesdb_many("Tetris", max_results=1, system="Game Boy")

            self.assertEqual(len(results), 1)
            self.assertEqual(urls, ["https://cdn.example/images/original/boxart/front/7.png"])

    def test_thegamesdb_platform_cache_is_used(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp), tgdb_key_var=Value("test-key"))
            providers = APP_MODULE.Providers(app)
            expected = {"Nintendo Game Boy": 42}
            with patch.object(APP_MODULE, "request_json", return_value={"data": {"platforms": {"42": {"id": 42, "name": "Nintendo Game Boy"}}}}) as request:
                self.assertEqual(providers.thegamesdb_platforms(), expected)
                self.assertEqual(providers.thegamesdb_platforms(), expected)
                request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
