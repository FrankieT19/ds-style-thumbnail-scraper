from pathlib import Path
import tempfile
import unittest

from PIL import Image

from ezflash_gba_thumbs import write_ezflash_bmp
from thumbnail_output_paths import (
    infer_relative_rom_path,
    mirrored_thumbnail_path,
    relative_path_from_root,
)


class ThumbnailOutputPathTests(unittest.TestCase):
    def test_mirrors_rom_folder_and_filename(self):
        result = mirrored_thumbnail_path(
            Path("IMGS"), "Game Boy/T/Tetris (World).gb"
        )
        self.assertEqual(
            result.as_posix(), "IMGS/Game Boy/T/Tetris (World).bmp"
        )

    def test_mirrors_box_art_to_same_tree_below_imgs2(self):
        result = mirrored_thumbnail_path(
            Path("IMGS2"), "Nintendo Entertainment System/A/Alwa's Awakening.nes"
        )
        self.assertEqual(
            result.as_posix(),
            "IMGS2/Nintendo Entertainment System/A/Alwa's Awakening.bmp",
        )

    def test_art_stem_is_always_rom_filename_stem_by_default(self):
        result = mirrored_thumbnail_path(Path("IMGS"), "Game Boy/T/Tetris.gb")
        self.assertEqual(result.name, "Tetris.bmp")

    def test_explicit_stem_can_be_supplied(self):
        result = mirrored_thumbnail_path(
            Path("IMGS"), "Game Boy/T/Tetris.gb", "Tetris (World)"
        )
        self.assertEqual(result.name, "Tetris (World).bmp")

    def test_same_title_in_two_systems_has_distinct_targets(self):
        game_boy = mirrored_thumbnail_path(
            Path("IMGS"), "Game Boy/T/Tetris.gb"
        )
        nes = mirrored_thumbnail_path(
            Path("IMGS"), "Nintendo Entertainment System/T/Tetris.nes"
        )
        self.assertNotEqual(game_boy, nes)

    def test_nested_output_is_written_as_ezflash_bmp(self):
        with tempfile.TemporaryDirectory() as output_dir:
            target = mirrored_thumbnail_path(
                Path(output_dir) / "IMGS", "Game Boy/T/Tetris.gb"
            )
            write_ezflash_bmp(Image.new("RGB", (120, 80), (30, 90, 160)), target)
            self.assertTrue(target.is_file())
            with Image.open(target) as image:
                self.assertEqual(image.size, (120, 80))

    def test_rejects_absolute_path(self):
        with self.assertRaises(ValueError):
            mirrored_thumbnail_path(Path("IMGS"), "/Game Boy/T/Tetris.gb")

    def test_rejects_parent_traversal(self):
        with self.assertRaises(ValueError):
            mirrored_thumbnail_path(Path("IMGS"), "../Tetris.gb")

    def test_rejects_windows_drive_path(self):
        with self.assertRaises(ValueError):
            mirrored_thumbnail_path(Path("IMGS"), "C:/ROMs/Tetris.gb")

    def test_infers_path_from_console_folder(self):
        path = Path("/mnt/roms/Game Boy/T/Tetris.gb")
        self.assertEqual(
            infer_relative_rom_path(path, "Game Boy"), "Game Boy/T/Tetris.gb"
        )

    def test_infer_returns_empty_if_system_anchor_is_missing(self):
        path = Path("/mnt/roms/T/Tetris.gb")
        self.assertEqual(infer_relative_rom_path(path, "Game Boy"), "")

    def test_sd_root_scan_preserves_relative_path(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            rom = root / "Game Boy" / "T" / "Tetris.gb"
            rom.parent.mkdir(parents=True)
            rom.touch()
            self.assertEqual(
                relative_path_from_root(root, rom, "Game Boy"),
                "Game Boy/T/Tetris.gb",
            )

    def test_selecting_system_folder_as_root_keeps_system_prefix(self):
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir) / "Game Boy"
            rom = root / "T" / "Tetris.gb"
            rom.parent.mkdir(parents=True)
            rom.touch()
            self.assertEqual(
                relative_path_from_root(root, rom, "Game Boy"),
                "Game Boy/T/Tetris.gb",
            )


if __name__ == "__main__":
    unittest.main()
