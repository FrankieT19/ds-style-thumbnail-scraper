"""Offline coverage for the automatic provider fallback chain and real auth flow."""

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
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_provider_chain_test", APP_PATH)
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
    Image.new("RGB", (20, 32), (12, 30, 70)).save(stream, format="PNG")
    return stream.getvalue()


def make_provider_app(tmp_path):
    return SimpleNamespace(
        base_dir=Path(tmp_path),
        tgdb_key_var=Value("tgdb-key"),
        ss_dev_id_var=Value("ss-developer"),
        ss_dev_pass_var=Value("ss-developer-secret"),
        ss_user_var=Value(""),
        ss_pass_var=Value(""),
        igdb_client_var=Value("twitch-client-id"),
        igdb_secret_var=Value("twitch-client-secret"),
        igdb_token_var=Value(""),
    )


class ProviderFallbackChainTests(unittest.TestCase):
    def test_chain_order_is_tgdb_then_screenscraper_then_igdb(self):
        with tempfile.TemporaryDirectory() as temp:
            providers = APP_MODULE.Providers(make_provider_app(temp))
            libretro = Mock(side_effect=LookupError("libretro image miss"))
            tgdb = Mock(side_effect=LookupError("TGDB no match"))
            ss = Mock(return_value=[APP_MODULE.ProviderResult("ScreenScraper", "invalid", b"<html>bad</html>", "Game Boy")])
            expected = APP_MODULE.ProviderResult("IGDB", "Tetris cover", png_bytes(), "Game Boy")
            igdb = Mock(return_value=[expected])
            providers.search_libretro_many = libretro
            providers.search_thegamesdb_many = tgdb
            providers.search_screenscraper_many = ss
            providers.search_igdb_many = igdb

            result = providers.search_many("Libretro", "Tetris", max_results=1, system="Game Boy")

            self.assertEqual(result, [expected])
            libretro.assert_called_once_with("Tetris", 1, None, "Game Boy")
            tgdb.assert_called_once_with("Tetris", 1, system="Game Boy")
            ss.assert_called_once_with("Tetris", 1, system="Game Boy")
            igdb.assert_called_once_with("Tetris", 1, system="Game Boy")

    def test_igdb_obtains_oauth_token_and_filters_games_to_requested_system(self):
        with tempfile.TemporaryDirectory() as temp:
            providers = APP_MODULE.Providers(make_provider_app(temp))
            image = png_bytes()
            post_calls = []

            def fake_post_json(url, body, headers):
                post_calls.append((url, body, headers))
                if url.endswith("/platforms"):
                    return [{"id": 33, "name": "Game Boy", "slug": "game-boy"}]
                if url.endswith("/games"):
                    return [{"name": "Tetris", "cover": {"image_id": "cover123"}, "artworks": []}]
                raise AssertionError(f"Unexpected IGDB URL: {url}")

            with patch.object(
                APP_MODULE,
                "post_form_json",
                return_value={"access_token": "oauth-token", "expires_in": 3600},
            ) as token_request, patch.object(APP_MODULE, "post_json", side_effect=fake_post_json), patch.object(
                APP_MODULE, "fetch_bytes", return_value=image
            ):
                results = providers.search_igdb_many("Tetris", max_results=1, system="Game Boy")

            token_request.assert_called_once_with(
                "https://id.twitch.tv/oauth2/token",
                {
                    "client_id": "twitch-client-id",
                    "client_secret": "twitch-client-secret",
                    "grant_type": "client_credentials",
                },
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].provider, "IGDB")
            self.assertEqual(results[0].system, "Game Boy")
            game_query = next(body for url, body, _headers in post_calls if url.endswith("/games"))
            self.assertIn("where platforms = (33)", game_query)
            self.assertTrue(all(call[2]["Authorization"] == "Bearer oauth-token" for call in post_calls))

    def test_screenscraper_search_uses_resolved_system_id_and_rejects_bad_image_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            providers = APP_MODULE.Providers(make_provider_app(temp))
            requested_urls = []

            def fake_request_json(url, _headers=None):
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if parsed.path.endswith("/systemesListe.php"):
                    return {
                        "response": {
                            "systemes": {
                                "systeme": [
                                    {"id": "9", "noms": {"nom_eu": "Nintendo Game Boy", "nom_us": "Game Boy"}},
                                    {"id": "12", "noms": {"nom_eu": "Nintendo Game Boy Advance"}},
                                ]
                            }
                        }
                    }
                if parsed.path.endswith("/jeuRecherche.php"):
                    self.assertEqual(params["systemeid"], ["9"])
                    self.assertEqual(params["recherche"], ["Tetris"])
                    return {
                        "response": {
                            "jeux": {
                                "jeu": {
                                    "id": "44",
                                    "nom": "Tetris",
                                    "medias": {
                                        "media": [
                                            {"type": "box-2D", "url": "https://cdn.example/bad.png"},
                                            {"type": "box-3D", "url": "https://cdn.example/good.png"},
                                        ]
                                    },
                                }
                            }
                        }
                    }
                raise AssertionError(f"Unexpected ScreenScraper URL: {url}")

            def fake_fetch(url, _headers=None):
                requested_urls.append(url)
                if url.endswith("bad.png"):
                    return b"not an image"
                return png_bytes()

            with patch.object(APP_MODULE, "request_json", side_effect=fake_request_json), patch.object(
                APP_MODULE, "fetch_bytes", side_effect=fake_fetch
            ):
                results = providers.search_screenscraper_many("Tetris", max_results=1, system="Game Boy")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].provider, "ScreenScraper")
            self.assertEqual(results[0].system, "Game Boy")
            self.assertEqual(requested_urls, ["https://cdn.example/bad.png", "https://cdn.example/good.png"])

    def test_screen_scraper_requires_developer_credentials_but_user_credentials_are_optional(self):
        with tempfile.TemporaryDirectory() as temp:
            app = make_provider_app(temp)
            app.ss_dev_id_var = Value("")
            providers = APP_MODULE.Providers(app)
            with self.assertRaisesRegex(LookupError, "developer ID"):
                providers._screenscraper_credentials()

            app.ss_dev_id_var = Value("developer")
            app.ss_dev_pass_var = Value("password")
            params = providers._screenscraper_credentials()
            self.assertEqual(params["devid"], "developer")
            self.assertNotIn("ssid", params)
            app.ss_user_var = Value("username")
            with self.assertRaisesRegex(LookupError, "both be filled"):
                providers._screenscraper_credentials()


if __name__ == "__main__":
    unittest.main()
