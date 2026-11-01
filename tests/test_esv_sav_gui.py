import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_esv_sav_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)

from goomba_save_converter import (  # noqa: E402
    GoombaSave,
    build_goomba_archive,
    extract_goomba_saves,
)


class FakeTree:
    def __init__(self, selection):
        self._selection = selection

    def selection(self):
        return self._selection


class FakeButton:
    def __init__(self):
        self.state = None

    def configure(self, **kwargs):
        self.state = kwargs["state"]


class FakeValue:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class ImmediateThread:
    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


class ESVSavGuiTests(unittest.TestCase):
    def _app(self, saver_folder, selection, files):
        app = object.__new__(APP_MODULE.ThumbnailScraperApp)
        app.esv_saver_folder_var = FakeValue(str(saver_folder))
        app.esv_saver_tree = FakeTree(selection)
        app.esv_scan_file_by_iid = files
        app.esv_conversion_running = False
        app.confirmation_prompts = 0
        app._confirm_esv_conversion = lambda: (
            setattr(app, "confirmation_prompts", app.confirmation_prompts + 1) or True
        )
        app._begin_esv_conversion = lambda _heading: True
        app.progress_events = []
        app.queue_operation_progress = (
            lambda *args, **kwargs: app.progress_events.append((args, kwargs))
        )
        app.after = lambda _delay, callback: callback()
        app.finished_conversions = []
        app._finish_esv_conversion = (
            lambda status, failures=None, error=None: app.finished_conversions.append(
                (status, failures, error)
            )
        )
        return app

    def test_conversion_confirmation_warns_about_save_data_loss(self):
        app = object.__new__(APP_MODULE.ThumbnailScraperApp)
        with patch.object(APP_MODULE.messagebox, "askyesno", return_value=True) as prompt:
            self.assertTrue(APP_MODULE.ThumbnailScraperApp._confirm_esv_conversion(app))

        self.assertIn("loss", prompt.call_args.args[1].casefold())
        self.assertIn("back up", prompt.call_args.args[1].casefold())

    def test_conversion_buttons_follow_selected_file_types(self):
        app = object.__new__(APP_MODULE.ThumbnailScraperApp)
        esv_file = Path("game.esv")
        sav_file = Path("game.sav")
        app.esv_scan_file_by_iid = {"esv": esv_file, "sav": sav_file}
        app.esv_saver_tree = FakeTree(["esv"])
        app.esv_conversion_running = False
        app.esv_extract_button = FakeButton()
        app.esv_build_button = FakeButton()

        APP_MODULE.ThumbnailScraperApp._update_esv_conversion_buttons(app)
        self.assertEqual(app.esv_extract_button.state, "normal")
        self.assertEqual(app.esv_build_button.state, "disabled")

        app.esv_saver_tree = FakeTree(["sav"])
        APP_MODULE.ThumbnailScraperApp._update_esv_conversion_buttons(app)
        self.assertEqual(app.esv_extract_button.state, "disabled")
        self.assertEqual(app.esv_build_button.state, "normal")

        app.esv_saver_tree = FakeTree([])
        APP_MODULE.ThumbnailScraperApp._update_esv_conversion_buttons(app)
        self.assertEqual(app.esv_extract_button.state, "disabled")
        self.assertEqual(app.esv_build_button.state, "disabled")

    def test_extract_converts_only_selected_esv_archives_in_background_worker(self):
        with tempfile.TemporaryDirectory() as temporary:
            saver_folder = Path(temporary) / "SYSTEM" / "SAVER"
            saver_folder.mkdir(parents=True)
            selected = saver_folder / "selected.esv"
            unselected = saver_folder / "unselected.esv"
            selected.write_bytes(
                build_goomba_archive([GoombaSave("SELECTED GAME", b"a" * 8192, 1)])
            )
            unselected.write_bytes(
                build_goomba_archive([GoombaSave("OTHER GAME", b"b" * 8192, 2)])
            )
            app = self._app(
                saver_folder,
                ["selected"],
                {"selected": selected, "unselected": unselected},
            )

            with patch.object(APP_MODULE.threading, "Thread", ImmediateThread):
                APP_MODULE.ThumbnailScraperApp.convert_esv_files_to_sav(app)

            selected_output = saver_folder / "SELECTED GAME.sav"
            unselected_output = saver_folder / "OTHER GAME.sav"
            self.assertEqual(selected_output.read_bytes(), b"a" * 8192)
            self.assertFalse(unselected_output.exists())
            self.assertEqual(len(app.finished_conversions), 1)
            self.assertEqual(app.confirmation_prompts, 1)
            self.assertTrue(
                any("Extracting archive" in event[0][1] for event in app.progress_events)
            )

    def test_sav_conversion_matches_only_selected_sav_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saver_folder = root / "SYSTEM" / "SAVER"
            saver_folder.mkdir(parents=True)
            selected = saver_folder / "SELECTED GAME.sav"
            unselected = saver_folder / "OTHER GAME.sav"
            selected.write_bytes(b"a" * 8192)
            unselected.write_bytes(b"b" * 8192)
            for title in ("SELECTED GAME", "OTHER GAME"):
                rom = bytearray(0x8000)
                rom[0x134:0x143] = title.encode("ascii").ljust(15, b"\0")
                (root / f"{title}.gb").write_bytes(rom)
            destination = saver_folder / "created.esv"
            app = self._app(
                saver_folder,
                ["selected"],
                {"selected": selected, "unselected": unselected},
            )

            with (
                patch.object(APP_MODULE.threading, "Thread", ImmediateThread),
                patch.object(
                    APP_MODULE.filedialog,
                    "asksaveasfilename",
                    return_value=str(destination),
                ),
            ):
                APP_MODULE.ThumbnailScraperApp.convert_sav_files_to_esv(app)

            converted = extract_goomba_saves(destination.read_bytes())
            self.assertEqual([save.title for save in converted], ["SELECTED GAME"])
            self.assertEqual(converted[0].data, b"a" * 8192)
            self.assertEqual(len(app.finished_conversions), 1)
            self.assertEqual(app.confirmation_prompts, 1)
            self.assertTrue(
                any("Indexing GB/GBC ROMs" in event[0][1] for event in app.progress_events)
            )


if __name__ == "__main__":
    unittest.main()
