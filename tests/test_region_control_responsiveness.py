"""Regression tests for responsive region controls and preview refreshes."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_region_responsiveness_test", APP_PATH)
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


class RegionControlResponsivenessTests(unittest.TestCase):
    def test_build_priority_change_only_schedules_debounced_build_preview(self):
        app = SimpleNamespace(_schedule_build_preview_search=Mock())

        APP_MODULE.ThumbnailScraperApp.on_region_change(app, scope="build")

        app._schedule_build_preview_search.assert_called_once_with(delay=650)

    def test_preview_priority_change_reorders_local_results_without_provider_search(self):
        app = SimpleNamespace(
            result_options=[object(), object()],
            _schedule_preview_gallery_refresh=Mock(),
            status_var=Value("Ready"),
            preview_search=Mock(),
            build_preview_search=Mock(),
        )

        APP_MODULE.ThumbnailScraperApp.on_region_change(app, scope="preview", update_suggestions=False)

        app._schedule_preview_gallery_refresh.assert_called_once_with()
        app.preview_search.assert_not_called()
        app.build_preview_search.assert_not_called()

    def test_preview_region_toggle_debounces_local_suggestions(self):
        app = SimpleNamespace(
            result_options=[],
            hide_suggestions=Mock(),
            _schedule_suggestion_refresh=Mock(),
            update_suggestions=Mock(),
            status_var=Value("Ready"),
            preview_search=Mock(),
            build_preview_search=Mock(),
        )

        APP_MODULE.ThumbnailScraperApp.on_region_change(app, scope="preview", update_suggestions=True)

        app.hide_suggestions.assert_called_once_with()
        app._schedule_suggestion_refresh.assert_called_once_with()
        app.update_suggestions.assert_not_called()
        app.preview_search.assert_not_called()
        app.build_preview_search.assert_not_called()

    def test_game_region_checkbox_defers_settings_save(self):
        app = SimpleNamespace(_schedule_settings_save=Mock())
        APP_MODULE.ThumbnailScraperApp.on_rom_region_change(app)
        app._schedule_settings_save.assert_called_once_with()

    def test_repeated_build_preview_requests_coalesce_to_latest_timer(self):
        app = SimpleNamespace(
            _build_preview_generation=0,
            _build_preview_pending=False,
            _build_preview_after_id=None,
            _set_build_preview_loading=Mock(),
            _start_scheduled_build_preview_search=Mock(),
            after=Mock(side_effect=["timer-1", "timer-2"]),
            after_cancel=Mock(),
            status_var=Value("Ready"),
        )

        APP_MODULE.ThumbnailScraperApp._schedule_build_preview_search(app, delay=650)
        self.assertEqual(app._build_preview_after_id, "timer-1")
        APP_MODULE.ThumbnailScraperApp._schedule_build_preview_search(app, delay=650)

        self.assertEqual(app._build_preview_generation, 2)
        self.assertEqual(app._build_preview_after_id, "timer-2")
        app.after_cancel.assert_called_once_with("timer-1")
        self.assertEqual(app.after.call_args.args[0], 650)
        self.assertTrue(app._build_preview_pending)
        app._set_build_preview_loading.assert_called_with(True, "Region settings changed; waiting to refresh the build preview…")

    def test_settings_save_debounces_rapid_region_edits(self):
        app = SimpleNamespace(
            _settings_save_after_id=None,
            after=Mock(side_effect=["save-1", "save-2"]),
            after_cancel=Mock(),
            _run_scheduled_settings_save=Mock(),
            status_var=Value("Ready"),
        )

        APP_MODULE.ThumbnailScraperApp._schedule_settings_save(app)
        APP_MODULE.ThumbnailScraperApp._schedule_settings_save(app)

        app.after_cancel.assert_called_once_with("save-1")
        self.assertEqual(app._settings_save_after_id, "save-2")
        self.assertEqual(app.after.call_args.args[0], 550)
        self.assertEqual(app.status_var.get(), "Saving region settings…")

    def test_noncredential_settings_save_preserves_provider_catalogue_caches(self):
        with tempfile.TemporaryDirectory() as temp:
            app = SimpleNamespace(
                config_path=Path(temp) / "settings.json",
                local_pack_var=Value(""),
                build_provider_var=Value("Libretro"),
                preview_provider_var=Value("Libretro"),
                preview_system_var=Value(APP_MODULE.DEFAULT_SYSTEM),
                build_libretro_source_var=Value("Box Art"),
                preview_libretro_source_var=Value("Box Art"),
                region_order=list(APP_MODULE.REGION_ORDER),
                region_enabled={region: True for region in APP_MODULE.REGION_ORDER},
                rom_region_vars={region: Value(True) for region in APP_MODULE.REGION_ORDER},
                igdb_client_var=Value("client"),
                igdb_secret_var=Value("secret"),
                igdb_token_var=Value("legacy-token"),
                tgdb_key_var=Value("key"),
                ss_dev_id_var=Value("dev"),
                ss_dev_pass_var=Value("dev-pass"),
                ss_user_var=Value("user"),
                ss_pass_var=Value("pass"),
                exceptions=[],
                custom_roms=[],
                custom_output_layout_var=Value("Mirror ROM folders"),
                status_var=Value("Ready"),
                providers=SimpleNamespace(
                    _igdb_access_token="cached-token",
                    _igdb_token_expires_at=12345.0,
                    _igdb_platform_ids={"Game Boy": 3},
                    _igdb_platform_catalog=[{"id": 3}],
                    _screenscraper_system_records=[{"id": 12}],
                ),
            )
            app._provider_credentials_snapshot = MethodType(
                APP_MODULE.ThumbnailScraperApp._provider_credentials_snapshot, app
            )
            app._saved_provider_credentials = app._provider_credentials_snapshot()

            APP_MODULE.ThumbnailScraperApp.save_settings(app)

            self.assertEqual(app.providers._igdb_access_token, "cached-token")
            self.assertEqual(app.providers._igdb_platform_ids, {"Game Boy": 3})
            self.assertEqual(app.providers._screenscraper_system_records, [{"id": 12}])

            app.tgdb_key_var.set("changed-key")
            APP_MODULE.ThumbnailScraperApp.save_settings(app)

            self.assertEqual(app.providers._igdb_access_token, "")
            self.assertEqual(app.providers._igdb_token_expires_at, 0.0)
            self.assertEqual(app.providers._igdb_platform_ids, {})
            self.assertIsNone(app.providers._igdb_platform_catalog)
            self.assertIsNone(app.providers._screenscraper_system_records)


if __name__ == "__main__":
    unittest.main()
