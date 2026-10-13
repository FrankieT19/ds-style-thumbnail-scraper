"""Regression tests for local-pack-first lookups and read-only artwork sources."""
import importlib.util
import io
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_local_pack_priority_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def png_bytes(color):
    stream = io.BytesIO()
    Image.new("RGB", (24, 32), color).save(stream, format="PNG")
    return stream.getvalue()


class LocalPackPriorityTests(unittest.TestCase):
    def test_return_keeps_selected_scan_game_attached_to_manual_search(self):
        game = {"title": "Crush Roller.ngc", "system": "Neo Geo Pocket", "path": "sd/Crush Roller.ngc"}
        app = SimpleNamespace(active_sd_scan_game=game)

        APP_MODULE.ThumbnailScraperApp.clear_active_sd_scan_game(
            app, SimpleNamespace(keysym="Return")
        )
        self.assertIs(app.active_sd_scan_game, game)

        APP_MODULE.ThumbnailScraperApp.clear_active_sd_scan_game(
            app, SimpleNamespace(keysym="a")
        )
        self.assertIsNone(app.active_sd_scan_game)

    def test_parent_variant_named_folders_do_not_penalize_retail_art(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            retail = root / "GBA" / "Demos" / "Tetris.png"
            demo = root / "GBA" / "Box Art" / "Tetris (Demo).png"
            retail.parent.mkdir(parents=True)
            demo.parent.mkdir(parents=True)
            retail.write_bytes(png_bytes((10, 200, 10)))
            demo.write_bytes(png_bytes((200, 10, 10)))
            app = SimpleNamespace(
                local_pack_var=Value(str(root)), region_allowed=lambda _title: True,
                region_priority=lambda _title: 0,
            )
            results = APP_MODULE.Providers(app).search_local_pack_many(
                "Tetris", max_results=2, system="Game Boy Advance"
            )
            self.assertTrue(results)
            self.assertEqual(results[0].image_data, retail.read_bytes())

    def test_local_pack_scopes_to_console_folder_through_arbitrary_nesting_and_reads_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "large media collection"
            gba = root / "GBA" / "Box Art" / "USA" / "Nested" / "Tetris (USA).png"
            nes = root / "Nintendo Entertainment System" / "Screenshots" / "Tetris (USA).png"
            gba.parent.mkdir(parents=True)
            nes.parent.mkdir(parents=True)
            gba_data = png_bytes((15, 200, 30))
            nes_data = png_bytes((220, 20, 20))
            gba.write_bytes(gba_data)
            nes.write_bytes(nes_data)
            original_files = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            app = SimpleNamespace(
                local_pack_var=Value(str(root)),
                local_pack_priority_var=Value(True),
                region_allowed=lambda _title: True,
                region_priority=lambda _title: 0,
            )
            providers = APP_MODULE.Providers(app)

            result = providers.search_local_pack_many("Tetris (USA)", max_results=1, system="Game Boy Advance")[0]

            self.assertEqual(result.provider, "Local Pack")
            self.assertIn("GBA", result.label)
            self.assertEqual(result.image_data, gba_data)
            self.assertNotIn("Nintendo Entertainment System", result.label)
            self.assertEqual({path: path.read_bytes() for path in root.rglob("*") if path.is_file()}, original_files)

    def test_priority_returns_local_art_before_selected_online_provider(self):
        app = SimpleNamespace(local_pack_priority_var=Value(True), local_pack_var=Value("unused"))
        providers = APP_MODULE.Providers(app)
        local = APP_MODULE.ProviderResult("Local Pack", "GBA/Tetris.png", png_bytes((10, 120, 10)), "Game Boy Advance")
        providers.search_local_pack_many = Mock(return_value=[local])
        providers.search_libretro_many = Mock(return_value=[])

        results = providers.search_many("Libretro", "Tetris", max_results=1, system="Game Boy Advance")

        self.assertEqual(results, [local])
        providers.search_local_pack_many.assert_called_once_with("Tetris", 1, system="Game Boy Advance")
        providers.search_libretro_many.assert_not_called()

    def test_priority_disabled_keeps_selected_provider_behavior(self):
        app = SimpleNamespace(local_pack_priority_var=Value(False), local_pack_var=Value("unused"))
        providers = APP_MODULE.Providers(app)
        online = APP_MODULE.ProviderResult("Libretro", "Tetris.png", png_bytes((10, 20, 220)), "Game Boy Advance")
        providers.search_libretro_many = Mock(return_value=[online])
        providers.search_local_pack_many = Mock(return_value=[])

        results = providers.search_many("Libretro", "Tetris", max_results=1, system="Game Boy Advance")

        self.assertEqual(results, [online])
        providers.search_libretro_many.assert_called_once()
        providers.search_local_pack_many.assert_not_called()

    def test_sd_scan_prefers_local_pack_over_existing_thumbnail_and_stale_rom_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            sd_root = temp_root / "sd"
            rom = sd_root / "Game Boy" / "T" / "Tetris (USA) (Rev 1) [!].gb"
            rom.parent.mkdir(parents=True)
            rom.write_bytes(b"sample ROM bytes")
            relative = "Game Boy/T/Tetris (USA) (Rev 1) [!].gb"

            pack_root = temp_root / "local media"
            local_source = pack_root / "Game Boy" / "Art" / "Deep" / "Tetris (USA).png"
            local_source.parent.mkdir(parents=True)
            fresh = png_bytes((25, 180, 40))
            local_source.write_bytes(fresh)
            source_before = local_source.read_bytes()

            cache_identity = f"game boy\0box art\0{relative.casefold()}"
            cache_digest = hashlib.sha256(cache_identity.encode("utf-8")).hexdigest()[:32]
            stale_cache = temp_root / "app" / "DS Style Thumbnail Scraper Cache" / "SD scan ROM artwork" / f"{cache_digest}.png"
            stale_cache.parent.mkdir(parents=True)
            stale_cache.write_bytes(png_bytes((200, 10, 10)))
            old_output = sd_root / "SYSTEM" / "IMGS2" / "Game Boy" / "T"
            old_output.mkdir(parents=True)
            Image.new("RGB", (80, 80), (200, 10, 10)).save(
                old_output / "Tetris (USA) (Rev 1) [!].bmp", format="BMP"
            )

            class ScanProviders:
                def __init__(self):
                    self.online_calls = []
                    self.hash_calls = []

                def search_local_pack_many(self, query, max_results=1, system=APP_MODULE.DEFAULT_SYSTEM):
                    return [APP_MODULE.ProviderResult("Local Pack", str(local_source.relative_to(pack_root)), local_source.read_bytes(), system)]

                def find_libretro_art_name(self, *args):
                    self.online_calls.append("Libretro")
                    return None

                def search_fallback_many(self, *args, **kwargs):
                    self.online_calls.append("Online fallback")
                    raise LookupError("unexpected online lookup")

                def search_hash_fallback(self, *args, **kwargs):
                    self.hash_calls.append(args)
                    raise LookupError("unexpected hash lookup")

            app = object.__new__(APP_MODULE.ThumbnailScraperApp)
            app.base_dir = temp_root / "app"
            app.custom_roms = []
            app.providers = ScanProviders()
            app.local_pack_priority_var = Value(True)
            app.local_pack_var = Value(str(pack_root))
            app.after = lambda _delay, callback: callback()
            app.status_var = Value("Ready")
            app.ask_sd_download_fallback_skip = lambda *_args: "skip"

            result = APP_MODULE.ThumbnailScraperApp._scan_sd_worker(
                app, sd_root, "Box Art", ["80x80"], False, use_hash_matching=True
            )

            self.assertEqual(result["matched_files"], 1)
            self.assertEqual(len(result["additions"]), 1)
            refreshed_cache = Path(result["additions"][0].image_path)
            with Image.open(refreshed_cache) as image:
                self.assertEqual(image.convert("RGB").getpixel((0, 0)), (25, 180, 40))
            self.assertEqual(local_source.read_bytes(), source_before)
            self.assertEqual(app.providers.online_calls, [])
            self.assertEqual(app.providers.hash_calls, [])

    def test_overwrite_cache_refreshes_stale_copy_without_touching_source_file(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "Local Pack" / "GBA" / "Box Art" / "Tetris.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(png_bytes((25, 180, 40)))
            before = source.read_bytes()
            cache = Path(temp) / "scraper cache" / "tetris.png"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(png_bytes((200, 10, 10)))
            app = object.__new__(APP_MODULE.ThumbnailScraperApp)

            APP_MODULE.ThumbnailScraperApp.cache_sd_scan_image(app, cache, before, overwrite=True)

            self.assertEqual(source.read_bytes(), before)
            with Image.open(cache) as image:
                self.assertEqual(image.convert("RGB").getpixel((0, 0)), (25, 180, 40))


if __name__ == "__main__":
    unittest.main()
