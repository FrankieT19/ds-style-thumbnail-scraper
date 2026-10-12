"""Offline API-shape tests for opt-in hash-based provider matching."""
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_hash_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


def png_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (20, 30), (25, 70, 110)).save(stream, format="PNG")
    return stream.getvalue()


def provider_app(tmp_path):
    return SimpleNamespace(
        base_dir=Path(tmp_path),
        tgdb_key_var=Value("tgdb-key"),
        ss_dev_id_var=Value("dev-id"),
        ss_dev_pass_var=Value("dev-password"),
        ss_user_var=Value(""),
        ss_pass_var=Value(""),
        igdb_client_var=Value(""),
        igdb_secret_var=Value(""),
        igdb_token_var=Value(""),
    )


class HashProviderTests(unittest.TestCase):
    def test_thegamesdb_hash_endpoint_is_platform_and_hash_type_filtered(self):
        with tempfile.TemporaryDirectory() as temp:
            providers = APP_MODULE.Providers(provider_app(temp))
            providers.thegamesdb_platform_id = Mock(return_value=18)
            payload = {
                "data": {"games": [{"id": 44, "game_title": "Tetris", "platform": 18}]},
                "include": {
                    "boxart": {
                        "base_url": {"original": "https://cdn.example/"},
                        "data": {"44": [{"side": "front", "filename": "/images/tetris-front.png"}]},
                    }
                },
            }
            calls = []

            def fake_request(url, _headers=None):
                calls.append(url)
                return payload

            with patch.object(APP_MODULE, "request_json", side_effect=fake_request), patch.object(
                APP_MODULE, "fetch_bytes", return_value=png_bytes()
            ):
                results = providers.search_thegamesdb_hash_many(
                    {"crc": "352441C2", "md5": "900150983cd24fb0d6963f7d28e17f72", "sha1": "a999", "size": 3},
                    "Tetris", max_results=1, system="Game Boy",
                )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].provider, "TheGamesDB")
            self.assertIn("ROM CRC match", results[0].label)
            params = parse_qs(urlparse(calls[0]).query)
            self.assertEqual(params["hash"], ["352441C2"])
            self.assertEqual(params["filter[type]"], ["crc"])
            self.assertEqual(params["filter[platform]"], ["18"])
            self.assertEqual(params["include"], ["boxart,platform"])

    def test_thegamesdb_tries_next_hash_type_when_crc_has_no_match(self):
        with tempfile.TemporaryDirectory() as temp:
            providers = APP_MODULE.Providers(provider_app(temp))
            providers.thegamesdb_platform_id = Mock(return_value=18)
            calls = []

            def fake_request(url, _headers=None):
                params = parse_qs(urlparse(url).query)
                calls.append(params["filter[type]"][0])
                if params["filter[type]"][0] == "crc":
                    return {"data": {"games": []}, "include": {"boxart": {}}}
                return {
                    "data": {"games": [{"id": 44, "game_title": "Tetris"}]},
                    "include": {
                        "boxart": {
                            "base_url": {"original": "https://cdn.example/"},
                            "data": {"44": [{"side": "front", "filename": "/images/front.png"}]},
                        }
                    },
                }

            with patch.object(APP_MODULE, "request_json", side_effect=fake_request), patch.object(
                APP_MODULE, "fetch_bytes", return_value=png_bytes()
            ):
                results = providers.search_thegamesdb_hash_many(
                    {"crc": "352441C2", "md5": "900150983cd24fb0d6963f7d28e17f72", "sha1": "a999", "size": 3},
                    "Tetris", max_results=1, system="Game Boy",
                )
            self.assertEqual(calls, ["crc", "md5"])
            self.assertEqual(len(results), 1)
            self.assertIn("ROM MD5 match", results[0].label)

    def test_screenscraper_hash_lookup_sends_all_hashes_and_file_size(self):
        with tempfile.TemporaryDirectory() as temp:
            providers = APP_MODULE.Providers(provider_app(temp))
            providers.screenscraper_system_id = Mock(return_value="9")
            rom_path = Path(temp) / "Tetris (USA) (Rev 1).gb"
            rom_path.write_bytes(b"abc")
            payload = {
                "response": {
                    "jeu": {
                        "id": "44",
                        "nom": "Tetris",
                        "medias": {"media": [{"type": "box-2D", "url": "https://cdn.example/tetris.png"}]},
                    }
                }
            }
            captured = []

            def fake_request(url, _headers=None):
                captured.append(url)
                return payload

            with patch.object(APP_MODULE, "request_json", side_effect=fake_request), patch.object(
                APP_MODULE, "fetch_bytes", return_value=png_bytes()
            ):
                results = providers.search_screenscraper_hash_many(
                    rom_path,
                    {"crc": "352441C2", "md5": "900150983cd24fb0d6963f7d28e17f72", "sha1": "a9993e364706816aba3e25717850c26c9cd0d89d", "size": 3},
                    "Tetris", max_results=1, system="Game Boy",
                )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].provider, "ScreenScraper")
            params = parse_qs(urlparse(captured[0]).query)
            self.assertEqual(params["systemeid"], ["9"])
            self.assertEqual(params["crc"], ["352441C2"])
            self.assertEqual(params["md5"], ["900150983cd24fb0d6963f7d28e17f72"])
            self.assertEqual(params["sha1"], ["a9993e364706816aba3e25717850c26c9cd0d89d"])
            self.assertEqual(params["romnom"], ["Tetris (USA) (Rev 1).gb"])
            self.assertEqual(params["romtaille"], ["3"])


if __name__ == "__main__":
    unittest.main()
