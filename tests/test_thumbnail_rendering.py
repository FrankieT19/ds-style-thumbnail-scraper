import io
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ezflash_gba_thumbs import write_ezflash_bmp
from thumbnail_rendering import fit_image_to_canvas, should_fit_art

# Load the app module without creating a Tk window so crop_image integration is also tested.
import importlib.util
import sys
APP_PATH = Path(__file__).resolve().parents[1] / "DS Style Thumbnail Scraper.py"
APP_SPEC = importlib.util.spec_from_file_location("thumbnail_scraper_crop_render_test", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(APP_SPEC)
sys.modules[APP_SPEC.name] = APP_MODULE
APP_SPEC.loader.exec_module(APP_MODULE)


class ThumbnailRenderingTests(unittest.TestCase):
    def test_only_non_square_box_art_uses_contain_fit(self):
        self.assertTrue(should_fit_art(Image.new("RGB", (2, 3)), (80, 80)))
        self.assertFalse(should_fit_art(Image.new("RGB", (80, 80)), (80, 80)))
        self.assertFalse(should_fit_art(Image.new("RGB", (120, 80)), (120, 80)))

    def test_portrait_art_is_centered_with_transparent_margins(self):
        source = Image.new("RGB", (20, 40), (200, 40, 40))
        fitted = fit_image_to_canvas(source, (80, 80))
        self.assertEqual(fitted.size, (80, 80))
        self.assertEqual(fitted.mode, "RGBA")
        self.assertEqual(fitted.getpixel((10, 40))[3], 0)
        self.assertEqual(fitted.getpixel((20, 40))[:3], (200, 40, 40))
        self.assertEqual(fitted.getpixel((20, 40))[3], 255)
        self.assertEqual(fitted.getpixel((59, 40))[3], 255)
        self.assertEqual(fitted.getpixel((60, 40))[3], 0)

    def test_crop_image_preserves_non_square_art_inside_80x80_target(self):
        source = Image.new("RGB", (20, 40), (180, 60, 30))
        fitted = APP_MODULE.crop_image(source, (80, 80), APP_MODULE.CropSettings())
        self.assertEqual(fitted.size, (80, 80))
        self.assertEqual(fitted.mode, "RGBA")
        self.assertEqual(fitted.getpixel((10, 40))[3], 0)
        self.assertEqual(fitted.getpixel((40, 40))[:3], (180, 60, 30))

    def test_visible_black_source_pixels_are_lifted_above_black_color_key(self):
        source = Image.new("RGB", (20, 40), (0, 0, 0))
        fitted = fit_image_to_canvas(source, (80, 80))
        self.assertEqual(fitted.getpixel((40, 40)), (8, 8, 8, 255))
        self.assertEqual(fitted.getpixel((0, 0)), (0, 0, 0, 0))

    def test_bmp_uses_zero_word_for_canvas_and_nonzero_word_for_source_black(self):
        fitted = fit_image_to_canvas(Image.new("RGB", (20, 40), (0, 0, 0)), (80, 80))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fitted.bmp"
            write_ezflash_bmp(fitted, path)
            data = path.read_bytes()
        pixel_offset = struct.unpack_from("<I", data, 10)[0]
        # Output BMP is top-down RGB555, each pixel is a little-endian word.
        corner_word = struct.unpack_from("<H", data, pixel_offset)[0]
        center_offset = pixel_offset + ((40 * 80) + 40) * 2
        center_word = struct.unpack_from("<H", data, center_offset)[0]
        self.assertEqual(corner_word, 0x0000, "canvas must use the kernel's black color key")
        self.assertEqual(center_word, (1 << 10) | (1 << 5) | 1, "source black should become RGB555 #080808")


if __name__ == "__main__":
    unittest.main()
