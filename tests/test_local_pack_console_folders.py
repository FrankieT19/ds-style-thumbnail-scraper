"""Regression tests for console-aware local-pack folder matching.

Covers the "Game Boy box art picked for the NES version of the same title" bug:
folder-name aliases for NES, Game Gear, Master System, TurboGrafx-16/PC Engine,
Neo Geo Pocket Color, Game Boy and Game Boy Color, nested console folders, and the
rule that art owned by another console is never borrowed.
"""
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "DS Style Thumbnail Scraper.py"
SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_local_pack_console_folders_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP_MODULE
SPEC.loader.exec_module(APP_MODULE)

NES = "Nintendo Entertainment System"
TITLE = "The Addams Family"


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


def make_providers(root):
    app = SimpleNamespace(
        local_pack_var=Value(str(root)),
        local_pack_priority_var=Value(True),
        region_allowed=lambda _title: True,
        region_priority=lambda _title: 0,
    )
    return APP_MODULE.Providers(app)


class Pack:
    """A throwaway media collection where every file has a unique color."""

    def __init__(self, temp):
        self.root = Path(temp) / "media collection"
        self.root.mkdir()
        self.colors = {}
        self._next = 10

    def add(self, *folders, name=f"{TITLE}.png"):
        path = self.root.joinpath(*folders, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        color = (self._next, 255 - self._next, 90)
        self._next += 7
        data = png_bytes(color)
        path.write_bytes(data)
        self.colors[data] = "/".join(folders)
        return data

    def lookup(self, system, title=TITLE):
        """Return the folder the chosen art came from, or None if nothing matched."""
        try:
            results = make_providers(self.root).search_local_pack_many(title, max_results=1, system=system)
        except LookupError:
            return None
        return self.colors[results[0].image_data]


class FolderAliasTests(unittest.TestCase):
    def test_every_alias_belongs_to_exactly_one_console(self):
        # Guards against aliases that collapse onto another console's name, for
        # example "Game Boy (Color)" -> "gameboy" when parentheses were stripped.
        for system, aliases in APP_MODULE.LOCAL_PACK_DIRECTORY_ALIASES.items():
            for alias in aliases:
                with self.subTest(system=system, alias=alias):
                    specific, broad = APP_MODULE.local_pack_folder_owners(alias)
                    self.assertEqual(specific, frozenset({system}))
                    self.assertFalse(broad)

    def test_other_console_names_never_overlap_supported_consoles(self):
        for name in APP_MODULE.LOCAL_PACK_OTHER_CONSOLE_FOLDERS:
            with self.subTest(name=name):
                specific, _broad = APP_MODULE.local_pack_folder_owners(name)
                self.assertEqual(specific, frozenset({APP_MODULE.LOCAL_PACK_OTHER_CONSOLE}))

    def test_no_folder_key_is_shared_between_supported_consoles(self):
        for key, owners in APP_MODULE.LOCAL_PACK_FOLDER_OWNERS.items():
            with self.subTest(key=key):
                self.assertEqual(len(owners), 1, f"{key!r} is claimed by {sorted(owners)}")

    def test_commonly_named_folders_resolve_to_the_expected_console(self):
        expected = {
            "NES": NES,
            "Nintendo Entertainment System": NES,
            "Original Nintendo": NES,
            "Famicom": NES,
            "nintendo-entertainment-system": NES,
            "Nintendo - Nintendo Entertainment System": NES,
            "Game Gear": "Game Gear",
            "Sega - Game Gear": "Game Gear",
            "gamegear": "Game Gear",
            "GG": "Game Gear",
            "Master System": "Master System",
            "mastersystem": "Master System",
            "Sega Master System": "Master System",
            "Sega - Master System - Mark III": "Master System",
            "SMS": "Master System",
            "TurboGrafx-16": "PC Engine",
            "TurboGrafx 16": "PC Engine",
            "TG-16": "PC Engine",
            "TG16": "PC Engine",
            "PC Engine": "PC Engine",
            "pcengine": "PC Engine",
            "NEC - PC Engine - TurboGrafx 16": "PC Engine",
            "Neo Geo Pocket Color": "Neo Geo Pocket Color",
            "SNK - Neo Geo Pocket Color": "Neo Geo Pocket Color",
            "NGPC": "Neo Geo Pocket Color",
            "Neo Geo Pocket Colour": "Neo Geo Pocket Color",
            "Game Boy": "Game Boy",
            "GameBoy": "Game Boy",
            "Nintendo - Game Boy": "Game Boy",
            "GB": "Game Boy",
            "Original Game Boy": "Game Boy",
            "Game Boy Color": "Game Boy Color",
            "Gameboy Colour": "Game Boy Color",
            "Nintendo - Game Boy Color": "Game Boy Color",
            "GBC": "Game Boy Color",
            # Text in brackets must not turn Game Boy Color into Game Boy.
            "Game Boy (Color)": "Game Boy Color",
            "Game Boy [Color]": "Game Boy Color",
            "Game Boy (DMG)": "Game Boy",
            # Parenthesised noise on an otherwise known name still resolves.
            "NES (USA)": NES,
            "Nintendo (NES)": NES,
            "Game Gear (Sega)": "Game Gear",
        }
        for folder, system in expected.items():
            with self.subTest(folder=folder):
                specific, _broad = APP_MODULE.local_pack_folder_owners(folder)
                self.assertEqual(specific, frozenset({system}))

    def test_bare_nintendo_is_a_broad_alias_for_nes_only(self):
        for folder in ("Nintendo", "nintendo", "Nintendo (USA)"):
            with self.subTest(folder=folder):
                specific, broad = APP_MODULE.local_pack_folder_owners(folder)
                self.assertFalse(specific)
                self.assertEqual(broad, frozenset({NES}))

    def test_unrelated_folder_names_are_not_consoles(self):
        for folder in ("Box Art", "Screenshots", "USA", "A", "Nintendo Power", "Capcom", "Sega"):
            with self.subTest(folder=folder):
                self.assertEqual(APP_MODULE.local_pack_folder_owners(folder), (frozenset(), frozenset()))


class CrossConsoleMatchingTests(unittest.TestCase):
    def test_every_alias_prefers_its_own_console_over_same_title_art_elsewhere(self):
        competitor = {
            NES: "Game Boy",
            "Game Gear": NES,
            "Master System": "Game Boy",
            "PC Engine": "Game Boy Color",
            "Neo Geo Pocket Color": "Master System",
            "Neo Geo Pocket": "Game Gear",
            "Game Boy": "Game Gear",
            "Game Boy Color": "Game Gear",
            "Game Boy Advance": "Game Gear",
        }
        for system, aliases in APP_MODULE.LOCAL_PACK_DIRECTORY_ALIASES.items():
            for folder in aliases:
                with self.subTest(system=system, folder=folder), tempfile.TemporaryDirectory() as temp:
                    pack = Pack(temp)
                    pack.add(competitor[system], "Box Art")
                    pack.add(folder, "Box Art")
                    pack.add("Nintendo", "Box Art", name="Some Other Game.png")
                    self.assertEqual(pack.lookup(system), f"{folder}/Box Art")

    def test_addams_family_uses_the_nintendo_folder_for_nes_not_game_boy(self):
        # The reported bug: NES lookup returned Game Boy art from a sibling folder.
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy", "Box Art")
            pack.add("Game Gear", "Box Art")
            pack.add("Super Nintendo", "Box Art")
            pack.add("Nintendo", "Box Art")
            self.assertEqual(pack.lookup(NES), "Nintendo/Box Art")
            self.assertEqual(pack.lookup("Game Boy"), "Game Boy/Box Art")
            self.assertEqual(pack.lookup("Game Gear"), "Game Gear/Box Art")

    def test_named_nes_folders_all_win_over_game_boy_art(self):
        for folder in ("NES", "Nintendo", "Original Nintendo", "Nintendo Entertainment System",
                       "Nintendo - Nintendo Entertainment System", "Famicom"):
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as temp:
                pack = Pack(temp)
                pack.add("Game Boy", "Box Art")
                pack.add(folder, "Box Art")
                self.assertEqual(pack.lookup(NES), f"{folder}/Box Art")

    def test_nested_console_folder_beats_a_broad_nintendo_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Nintendo", "Box Art")
            pack.add("Nintendo", "Game Boy", "Box Art")
            pack.add("Nintendo", "Game Boy Color", "Box Art")
            self.assertEqual(pack.lookup(NES), "Nintendo/Box Art")
            self.assertEqual(pack.lookup("Game Boy"), "Nintendo/Game Boy/Box Art")
            self.assertEqual(pack.lookup("Game Boy Color"), "Nintendo/Game Boy Color/Box Art")

    def test_nintendo_publisher_folder_inside_a_console_folder_does_not_hijack_it(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy Advance", "Box Art", "Nintendo", name="Mario Kart Super Circuit.png")
            pack.add("Nintendo", "Box Art", name="Mario Kart Super Circuit.png")
            self.assertEqual(
                pack.lookup("Game Boy Advance", "Mario Kart Super Circuit"),
                "Game Boy Advance/Box Art/Nintendo",
            )
            self.assertEqual(pack.lookup(NES, "Mario Kart Super Circuit"), "Nintendo/Box Art")

    def test_console_folder_can_sit_below_the_media_type_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Box Art", "Game Boy")
            pack.add("Box Art", "Original Nintendo")
            pack.add("Screenshots", "Original Nintendo", name="Other Game.png")
            self.assertEqual(pack.lookup(NES), "Box Art/Original Nintendo")
            self.assertEqual(pack.lookup("Game Boy"), "Box Art/Game Boy")

    def test_game_boy_and_game_boy_color_stay_separate_even_with_bracketed_names(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy (DMG)", "Box Art")
            pack.add("Game Boy (Color)", "Box Art")
            self.assertEqual(pack.lookup("Game Boy"), "Game Boy (DMG)/Box Art")
            self.assertEqual(pack.lookup("Game Boy Color"), "Game Boy (Color)/Box Art")

    def test_system_folder_without_the_title_does_not_fall_back_to_other_consoles(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy", "Box Art")
            pack.add("NES", "Box Art", name="Different Game.png")
            self.assertIsNone(pack.lookup(NES))

    def test_missing_console_folder_never_borrows_art_from_another_console(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy", "Box Art")
            pack.add("Super Nintendo", "Box Art")
            pack.add("Sega Genesis", "Box Art")
            pack.add("Arcade", "Box Art")
            for system in (NES, "Master System", "PC Engine", "Neo Geo Pocket Color", "Game Gear"):
                with self.subTest(system=system):
                    self.assertIsNone(pack.lookup(system))
            self.assertEqual(pack.lookup("Game Boy"), "Game Boy/Box Art")

    def test_unlabeled_folders_remain_usable_when_the_console_has_no_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy", "Box Art")
            pack.add("Misc Box Art")
            self.assertEqual(pack.lookup(NES), "Misc Box Art")
            self.assertEqual(pack.lookup("Game Boy"), "Game Boy/Box Art")

    def test_pack_with_no_console_folders_keeps_whole_pack_matching(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Box Art", "A")
            for system in (NES, "Game Boy", "Game Gear"):
                with self.subTest(system=system):
                    self.assertEqual(pack.lookup(system), "Box Art/A")

    def test_neo_geo_pocket_extensions_share_color_and_mono_folders(self):
        # .ngc files resolve to "Neo Geo Pocket", but their art normally lives in
        # a Neo Geo Pocket Color folder; neither may borrow from other consoles.
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy Color", "Box Art")
            pack.add("Neo Geo Pocket Color", "Box Art")
            self.assertEqual(pack.lookup("Neo Geo Pocket"), "Neo Geo Pocket Color/Box Art")
            self.assertEqual(pack.lookup("Neo Geo Pocket Color"), "Neo Geo Pocket Color/Box Art")
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy Color", "Box Art")
            self.assertIsNone(pack.lookup("Neo Geo Pocket"))
            self.assertIsNone(pack.lookup("Neo Geo Pocket Color"))

    def test_local_pack_is_never_modified(self):
        with tempfile.TemporaryDirectory() as temp:
            pack = Pack(temp)
            pack.add("Game Boy", "Box Art")
            pack.add("Nintendo", "Box Art")
            before = {path: path.read_bytes() for path in pack.root.rglob("*") if path.is_file()}
            pack.lookup(NES)
            pack.lookup("Game Boy")
            pack.lookup("Game Gear")
            after = {path: path.read_bytes() for path in pack.root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(
                {path.relative_to(pack.root) for path in pack.root.rglob("*")},
                {Path(p) for p in ("Game Boy", "Game Boy/Box Art", "Game Boy/Box Art/The Addams Family.png",
                                   "Nintendo", "Nintendo/Box Art", "Nintendo/Box Art/The Addams Family.png")},
            )


if __name__ == "__main__":
    unittest.main()
