"""Offline regression tests for retail-first artwork candidate ranking."""

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_retail_priority_test", APP_PATH)
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
    Image.new("RGB", (20, 32), (24, 75, 130)).save(stream, format="PNG")
    return stream.getvalue()


class RetailReleasePriorityTests(unittest.TestCase):
    def test_standard_retail_names_rank_ahead_of_common_variants(self):
        self.assertEqual(APP_MODULE.variant_rank("Tetris (USA).png"), 0)
        self.assertLess(APP_MODULE.variant_rank("Tetris [ROM CRC match]"), 0)
        self.assertLess(APP_MODULE.variant_rank("Tetris [ROM MD5 match]"), 0)
        self.assertLess(APP_MODULE.variant_rank("Tetris [ROM SHA1 match]"), 0)
        for variant in (
            "Tetris (Alpha).png",
            "Tetris (Beta).png",
            "Tetris (Proto).png",
            "Tetris (Prototype).png",
            "Tetris (Demo).png",
            "Tetris (Mod).png",
            "Tetris (Hack).png",
            "Tetris - Randomizer.png",
            "Tetris (Unreleased).png",
            "Tetris (Virtual Console).png",
            "Tetris [T+Eng].png",
        ):
            with self.subTest(variant=variant):
                self.assertGreater(APP_MODULE.variant_rank(variant), 0)

    def test_libretro_returns_retail_match_before_beta_when_limit_is_one(self):
        app = SimpleNamespace()
        providers = APP_MODULE.Providers(app)
        providers.get_libretro_index = lambda system, folder: [
            "Tetris (Beta).png",
            "Tetris.png",
        ]
        with patch.object(APP_MODULE, "http_get", return_value=png_bytes()):
            results = providers.search_libretro_many(
                "Tetris", max_results=1, libretro_source="Box Art", system="Game Boy"
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].label, "Tetris.png")

    def test_libretro_normalized_exact_match_uses_retail_art_even_for_beta_rom_name(self):
        app = SimpleNamespace(
            ordered_regions=lambda: ["USA", "Europe", "Japan", "Other"],
        )
        providers = APP_MODULE.Providers(app)
        providers.get_libretro_index = lambda _system, _folder: [
            "Tetris (Beta).png",
            "Tetris.png",
        ]

        selected = providers.find_libretro_art_name("Tetris (Beta).gba", "Game Boy", "Named_Boxarts")

        self.assertEqual(selected, "Tetris.png")

    def test_thegamesdb_sorts_retail_game_before_beta_before_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp), tgdb_key_var=Value("test-key"))
            providers = APP_MODULE.Providers(app)
            providers.thegamesdb_platform_id = lambda _system: 42
            response = {
                "data": {
                    "games": [
                        {"id": 1, "game_title": "Tetris (Beta)"},
                        {"id": 2, "game_title": "Tetris"},
                    ]
                },
                "include": {
                    "boxart": {
                        "base_url": {"original": "https://cdn.example/"},
                        "data": {
                            "1": [{"filename": "front/beta.png", "side": "front"}],
                            "2": [{"filename": "front/retail.png", "side": "front"}],
                        },
                    }
                },
            }
            with patch.object(APP_MODULE, "request_json", return_value=response), patch.object(
                APP_MODULE, "fetch_bytes", return_value=png_bytes()
            ) as fetch:
                results = providers.search_thegamesdb_many("Tetris", max_results=1, system="Game Boy")
            self.assertEqual(len(results), 1)
            self.assertIn("Tetris - retail.png", results[0].label)
            fetch.assert_called_once_with("https://cdn.example/front/retail.png")

    def test_screenscraper_sorts_retail_game_before_proto_before_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp))
            providers = APP_MODULE.Providers(app)
            providers._screenscraper_credentials = lambda: {"devid": "dev", "devpassword": "secret"}
            providers.screenscraper_system_id = lambda _system: "3"
            response = {
                "response": {
                    "jeux": {
                        "jeu": [
                            {"nom": "Tetris (Proto)", "medias": {"media": [{"type": "box-2D", "url": "https://cdn.example/proto.png"}]}},
                            {"nom": "Tetris", "medias": {"media": [{"type": "box-2D", "url": "https://cdn.example/retail.png"}]}},
                        ]
                    }
                }
            }
            with patch.object(APP_MODULE, "request_json", return_value=response), patch.object(
                APP_MODULE, "fetch_bytes", return_value=png_bytes()
            ) as fetch:
                results = providers.search_screenscraper_many("Tetris", max_results=1, system="Game Boy")
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].label.startswith("Tetris -"))
            fetch.assert_called_once_with("https://cdn.example/retail.png")

    def test_igdb_sorts_retail_game_before_hack_before_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(base_dir=Path(temp))
            providers = APP_MODULE.Providers(app)
            providers._igdb_auth_headers = lambda: {"Authorization": "Bearer token"}
            providers._igdb_platform_id = lambda _system, _headers: 42
            games = [
                {"name": "Tetris (Hack)", "cover": {"image_id": "hack"}, "artworks": []},
                {"name": "Tetris", "cover": {"image_id": "retail"}, "artworks": []},
            ]
            with patch.object(APP_MODULE, "post_json", return_value=games), patch.object(
                APP_MODULE, "fetch_bytes", return_value=png_bytes()
            ) as fetch:
                results = providers.search_igdb_many("Tetris", max_results=1, system="Game Boy")
            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].label.startswith("Tetris -"))
            fetch.assert_called_once_with("https://images.igdb.com/igdb/image/upload/t_720p/retail.jpg")


if __name__ == "__main__":
    unittest.main()
