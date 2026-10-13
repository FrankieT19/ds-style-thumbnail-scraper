"""Offline tests for JSON index cache recovery and network failure handling."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_thegamesdb_platform_cache_with_wrong_json_shape_is_refetched(self):
        class Value:
            def get(self):
                return "test-key"

        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "DS Style Thumbnail Scraper Cache" / "thegamesdb_platforms.json"
            cache.parent.mkdir(parents=True)
            cache.write_text("[]", encoding="utf-8")
            app = SimpleNamespace(base_dir=Path(temp), tgdb_key_var=Value())
            providers = APP.Providers(app)
            response = {"data": {"platforms": {"1": {"id": 1, "name": "Game Boy"}}}}
            with patch.object(APP, "request_json", return_value=response) as request:
                self.assertEqual(providers.thegamesdb_platforms(), {"Game Boy": 1})
            request.assert_called_once()

    def test_non_object_settings_json_is_ignored_without_startup_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            app = object.__new__(APP.ThumbnailScraperApp)
            app.config_path = Path(temp) / "settings.json"
            app.config_path.write_text("[]", encoding="utf-8")
            app._provider_credentials_snapshot = lambda: ()

            app._load_settings()

            self.assertEqual(app._saved_provider_credentials, ())

    def test_non_object_scan_report_metadata_is_reported_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "scan.txt"
            report.with_suffix(".json").write_text("[]", encoding="utf-8")
            app = object.__new__(APP.ThumbnailScraperApp)
            with patch.object(APP.filedialog, "askopenfilename", return_value=str(report)), patch.object(
                APP.messagebox, "showwarning"
            ) as warning:
                app.import_sd_scan_report()
            warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
