"""Regression tests for TheGamesDB credential checks and operation progress hooks."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_settings_progress_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)


class Value:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeProgressWindow:
    def __init__(self):
        self.calls = []

    def update_progress(self, heading, current=None, total=None, detail=""):
        self.calls.append((heading, current, total, detail))


class SettingsAndProgressTests(unittest.TestCase):
    @patch.object(APP_MODULE, "request_json")
    def test_thegamesdb_api_key_test_counts_platforms_from_fresh_response(self, request):
        request.return_value = {
            "data": {
                "platforms": {
                    "1": {"id": 1, "name": "Nintendo Game Boy"},
                    "2": {"id": 2, "name": "Nintendo Game Boy Advance"},
                    "junk": None,
                }
            }
        }

        count = APP_MODULE.Providers.test_thegamesdb_api_key("example-key")

        self.assertEqual(count, 2)
        request.assert_called_once()
        self.assertIn("apikey=example-key", request.call_args.args[0])
        self.assertIn("/v1/Platforms?", request.call_args.args[0])

    @patch.object(APP_MODULE, "request_json")
    def test_thegamesdb_api_key_test_rejects_response_without_platform_data(self, request):
        request.return_value = {"data": {"platforms": []}, "status": "Invalid API key"}
        with self.assertRaisesRegex(LookupError, "Invalid API key"):
            APP_MODULE.Providers.test_thegamesdb_api_key("bad-key")

    def test_thegamesdb_api_key_test_requires_a_key_without_network_request(self):
        with patch.object(APP_MODULE, "request_json") as request:
            with self.assertRaisesRegex(LookupError, "Enter your TheGamesDB API key"):
                APP_MODULE.Providers.test_thegamesdb_api_key("  ")
        request.assert_not_called()

    def test_progress_updates_are_dispatched_to_the_active_window_and_footer(self):
        app = object.__new__(APP_MODULE.ThumbnailScraperApp)
        status = Value()
        window = FakeProgressWindow()
        app.sd_scan_progress_window = window
        app.status_var = status
        app.after = lambda _delay, callback: callback()

        app.queue_operation_progress(
            "sd_scan_progress_window",
            "Matching installed games",
            4,
            10,
            "Game Boy: Tetris.gb",
        )

        self.assertEqual(
            window.calls,
            [("Matching installed games", 4, 10, "Game Boy: Tetris.gb")],
        )
        self.assertEqual(status.get(), "Matching installed games — Game Boy: Tetris.gb")

    def test_sd_file_enumeration_reports_folder_and_rom_counts(self):
        app = object.__new__(APP_MODULE.ThumbnailScraperApp)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Game Boy" / "T").mkdir(parents=True)
            (root / "Game Boy" / "T" / "Tetris.gb").touch()
            (root / "Game Boy" / "T" / "readme.txt").touch()
            events = []

            found = app.supported_files_on_sd(
                root,
                include_gba=False,
                progress_callback=lambda *args: events.append(args),
            )

        self.assertEqual(len(found), 1)
        self.assertTrue(events)
        self.assertEqual(events[-1][0], "SD card folder scan complete")
        self.assertIn("1 supported ROM files", events[-1][3])


if __name__ == "__main__":
    unittest.main()
