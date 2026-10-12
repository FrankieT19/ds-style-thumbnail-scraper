# Mirrored Artwork Output — Implementation Notes

## Output behavior

The Custom Art tab now defaults to **Mirror ROM folders**. For each ROM discovered during an SD-card scan, the scraper records the path relative to the chosen SD root. Artwork is emitted beneath `IMGS` and `IMGS2` with the same relative directories and the ROM filename stem:

- ROM: `Game Boy/T/Tetris (World).gb`
- Title artwork: `IMGS/Game Boy/T/Tetris (World).bmp` (120×80)
- Box artwork: `IMGS2/Game Boy/T/Tetris (World).bmp` (80×80)

The output preserves the ROM directory layout; it does not move ROMs or invent alphabet buckets. Scan the actual SD root so any grouping directories, console directories and letter buckets all remain part of the path.

## Compatibility and defaults

- The full GBA pack builder is unchanged.
- The Custom Art tab retains **Legacy CUSTOM** output for older kernel builds. The app enforces the 256 ordinary indexed-image limit per size only for artwork actually directed into flat `CUSTOM`.
- In Mirror mode, name-only entries still go to `CUSTOM`. That supports direct extension defaults such as `IMGS/CUSTOM/gb.bmp` and `IMGS2/CUSTOM/nes.bmp`, as expected by the modified kernel.
- Matching title stems in different ROM subfolders can now coexist because their mirror destinations are distinct.
- Saved custom-art settings gain an optional `rom_relative_path` field. Old settings remain loadable; paths can also be inferred for older items when their full path includes a directory exactly matching the supported system name.
- The mirrored path helper rejects absolute paths, parent traversal and invalid output stems before it writes outside the artwork root.

## Validation performed

- `python -m py_compile "DS Style Thumbnail Scraper.py" thumbnail_output_paths.py ezflash_gba_full_library.py ezflash_gba_pack_converter.py ezflash_gba_thumbs.py` — passed.
- Application module imported without starting the Tk window — passed; app version reports `1.6`.
- `python -m unittest discover -s tests -v` — 13 tests passed. Coverage includes title/box mirrored paths, same-title collisions in different systems, root/console-root path handling, invalid path rejection, and writing a valid 120×80 EZ-FLASH BMP at a nested path.

## Building the Windows executable

This environment is Linux and did not contain PyInstaller, PowerShell, or Wine, so a Windows `.exe` was not generated here. On Windows, install Python, then run `build.ps1` from the project folder. The script installs the project requirements and PyInstaller, then builds the executable from `DS Style Thumbnail Scraper.spec`.


## SD scan invalid-image handling (v1.6.1)

The Custom Art SD scan now fully decodes each downloaded artwork payload before adding it to the cache. This catches HTML/404 payloads, Git LFS pointer text, empty responses, and truncated images that can be returned by a raw-file endpoint. Invalid results are listed under the SD scan's download errors and skipped; other artwork matches continue to process. The cache entry point also validates data defensively so an invalid result produces a readable message instead of Pillow's raw `cannot identify image file` exception.

Validation performed for v1.6.1: Python compilation passed and 19 unit tests passed, including five payload-validation regressions and a scan-level integration test proving one invalid provider response does not stop other games from being processed. The Windows executable was not built in this Linux environment.


## v1.6.2 retry and incremental-scan additions

- A failed HTTP request or invalid image payload now opens a Retry Download / Skip Image prompt. Closing the dialog is treated as Skip.
- A persistent source cache is keyed by console, artwork type and provider artwork filename, so later scans reuse valid images without issuing another download.
- Before fetching, the scanner checks whether each requested thumbnail size already exists and is valid in the selected SD root's `SYSTEM/IMGS` / `SYSTEM/IMGS2`, root-level `IMGS` / `IMGS2`, or any previous timestamped scraper output folder. Correct-size images are skipped; corrupt or wrong-sized files are rebuilt.
- Prior v1.6.1 custom-art cache files referenced by saved entries can be migrated into the new keyed cache when another thumbnail size is requested.
- Regression tests cover Retry, Skip, the persistent cache, the old settings-linked cache, existing output thumbnails, and corrupt output files.


Current v1.6.2 validation: `python -m py_compile "DS Style Thumbnail Scraper.py" thumbnail_output_paths.py thumbnail_image_data.py` passed, and `python -m unittest discover -s tests -v` passed all 25 tests. The Windows executable was not built in this Linux environment.


## v1.7.0 additions

### TheGamesDB fallback

When a Libretro title lookup yields no usable match, the scraper can retry via TheGamesDB. It fetches the official platform list and matches the selected console to an explicit platform ID before querying `/v1.1/Games/ByGameName` with `filter[platform]`, requesting box art and platform metadata. A TheGamesDB API key must be entered under Settings → Provider Credentials. Platform IDs are cached for 30 days. The provider API documents the required API key and platform filtering in its official specification: https://api.thegamesdb.net/ and https://github.com/TheGamesDB/TheGamesDBv2/blob/master/API/spec.yaml.

### Aspect-preserving box art and black transparency key

For 80×80 output only, sources whose aspect ratio differs from square by more than 12% are contained, proportionally scaled and centered instead of cropped-to-fill. Empty canvas pixels use alpha 0 internally and are written as RGB555 zero (pure black) in the final BMP, which DS Style treats as its transparency key. Opaque pixels that would quantize to RGB555 zero are lifted to RGB555 (1,1,1), equivalent to #080808, so source black details remain visible. No kernel change is required.

### Verification

Added offline tests for Libretro→TheGamesDB fallback, platform filtering and image selection, Custom Art SD-scan fallback, centered contain-fit output, black-key padding and preservation of source-black details. Run `python -m unittest discover -s tests -v` and `python -m py_compile "DS Style Thumbnail Scraper.py" thumbnail_image_data.py thumbnail_output_paths.py thumbnail_rendering.py ezflash_gba_thumbs.py`.
