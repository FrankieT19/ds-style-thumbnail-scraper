## v1.9.1 cache-first scan ordering

The SD scan uses this order before any online artwork search:

1. Check all requested sizes for valid mirrored thumbnails under the selected SD root, root-level `IMGS`/`IMGS2`, and previous scraper output folders. Complete outputs are skipped without Libretro-index or provider lookup.
2. Reuse a valid image already referenced by a saved Custom Art entry for the ROM.
3. Check a persistent per-ROM source-image cache keyed by console, selected artwork type, and ROM-relative path. This key does not depend on the provider's current search-result label, so cached fallback-provider images are reusable too.
4. Only on a cache miss, look for a Libretro filename match and then download its image; if no usable Libretro result exists, try TheGamesDB, ScreenScraper, and IGDB in order.
5. Cache every newly accepted image by ROM identity as well as its provider/artwork identity. Subsequent scans can reuse it before asking any provider.

`Build Custom Art` itself reads the image paths already attached to Custom Art entries and converts them to BMP output; it does not call online providers. Provider lookup happens during scan/search, and the scan now honors cached source images first.

### v1.9.1 validation

- `python -m py_compile "DS Style Thumbnail Scraper.py" thumbnail_image_data.py thumbnail_output_paths.py thumbnail_rendering.py ezflash_gba_thumbs.py` — passed.
- `python -m unittest discover -s tests -v` — 50 tests passed, including cache-first checks for an existing thumbnail, saved cache from a prior scan, and cached TheGamesDB fallback results.
- Windows executable build and live provider requests were not run in this environment.

## v1.9.0 provider fallback and invalid-image choices

- Automatic lookup now follows the fixed sequence **Libretro → TheGamesDB → ScreenScraper → IGDB**. Each source must return fully decodable image data; an empty, HTML, truncated or otherwise invalid response is treated as a miss and the next configured provider is tried.
- ScreenScraper now uses the configured developer ID/password, optional user ID/password, `systemesListe.php` to resolve a console-specific system ID, and `jeuRecherche.php` to search that system. Media payloads are decoded/validated before they are accepted. The API documents `devid`, `devpassword`, `softname`, optional `ssid`/`sspassword`, `systemeid`, and `recherche`: https://www.screenscraper.fr/webapi2.php.
- IGDB now uses Twitch Client ID + Client Secret via the client-credentials OAuth flow, caches the token until shortly before expiry, discovers platform IDs from IGDB's platform endpoint, and restricts game searches to that platform. IGDB documents OAuth and the `Client-ID`/Bearer headers here: https://api-docs.igdb.com/ and https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/.
- The Settings tab exposes Client Secret (masked by default), provider-specific test actions, and links to API registration. Existing manually saved IGDB access tokens still work as a compatibility fallback if no Client Secret is entered, but new setup should use Client ID + Secret.
- On an invalid/incomplete raw Libretro download during SD scanning, the former **Retry Download** action is now **Try Fallback**. It tries TheGamesDB, ScreenScraper and IGDB in that order, writes the first valid image to the persistent cache, and continues. **Skip Image** still skips only the failed image. Providers used during normal automatic searches also skip invalid responses and continue down the chain without requiring a prompt.
- Credentials are stored in the local settings JSON. IGDB access tokens are held in memory during a session; changing credentials clears cached OAuth/platform lookup state.

### v1.9.0 validation

- `python -m py_compile "DS Style Thumbnail Scraper.py" thumbnail_image_data.py thumbnail_output_paths.py thumbnail_rendering.py ezflash_gba_thumbs.py` — passed.
- `python -m unittest discover -s tests -v` — passed; includes fallback order, IGDB OAuth/system filtering, ScreenScraper system resolution/media validation, and Try Fallback flow.
- Live API calls with the user's actual credentials and a fresh Windows executable build have not been performed in this environment.

# Mirrored Artwork Output — Implementation Notes

## v1.8.0 settings and operation progress

- The Settings tab provides a masked TheGamesDB API-key field with Show/Hide, a link to TheGamesDB's API page, and a **Test key** action. Testing performs a fresh `/v1/Platforms` API request instead of trusting the 30-day platform cache. TheGamesDB API access uses an API key, not the website login password.
- The Custom Art SD scan shows a live status window while walking directories and processing games, including counts, current console/game, provider fallback, cache checks and downloads. A continuously refreshed elapsed-time indicator helps distinguish slow work from a stalled window.
- Build Custom Art now writes thumbnails in a background worker and reports the current item, output path, progress percentage and elapsed time. The Tk event loop remains available while images are loaded and BMPs are generated.
- Added offline tests for API-key verification and progress callback dispatch. Run `python -m unittest discover -s tests -v` and `python -m py_compile "DS Style Thumbnail Scraper.py" thumbnail_image_data.py thumbnail_output_paths.py thumbnail_rendering.py ezflash_gba_thumbs.py`.

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

### v1.8.0 verification results

- `python -m py_compile "DS Style Thumbnail Scraper.py" thumbnail_image_data.py thumbnail_output_paths.py thumbnail_rendering.py ezflash_gba_thumbs.py` — passed.
- `python -m unittest discover -s tests -v` — 44 tests passed, including five new credential/progress tests.
- GUI smoke checks under Xvfb — passed: Settings tab loads with TheGamesDB key controls, Show/Hide works, the progress window updates between indeterminate/determinate phases, a Custom Art build generates a BMP in the background, and an SD scan reports progress and completes successfully.
- The Windows executable was not rebuilt in this Linux environment, and the live TheGamesDB key-validation request was covered with mocks rather than tested against a real key.


## v1.9.2 selective transparency marker

Newly generated BMPs receive the `DST1` signature in reserved BMP header bytes 6–9 only when their image contains pixels whose alpha is below the writer's transparency threshold. This is intended for aspect-preserving 80×80 box-art output with transparent padding. Opaque output remains unmarked, so existing GBA artwork and legacy CUSTOM artwork keep the old kernel drawing behavior. A compatible kernel build must recognize `DST1`; older kernels ignore the header bytes and will still draw the black padding as black.


## v1.10.0 — Optional hash-assisted matching

The SD Scan setup dialog now has an opt-in “Use ROM hash matching if name searches fail” toggle, off by default. Existing thumbnails and local source-image caches still take precedence. All online name matching is attempted first in the regular provider order; only after that chain returns no valid image does hash mode stream the ROM file once to compute CRC32, MD5, SHA-1 and file size. TheGamesDB hash lookup is attempted before ScreenScraper’s ROM identification endpoint. Libretro thumbnail lookup and IGDB do not have a documented direct ROM-file hash-to-art endpoint.

For name matching, known No-Intro-style tags (region/language/version/revision parentheses and square-bracket dump/status tags) are removed from a temporary search string. Original ROM names, mirrored output paths and per-ROM cache identities remain untouched. The current implementation hashes the supported ROM file as stored on disk; it does not unpack ZIP/7z/archive contents.


## v1.10.1 region-control responsiveness

The Build Pack region controls defer settings-file writes until the user pauses. Artwork-priority changes in Build Pack debounce preview provider lookups and display an indeterminate progress indicator with status text. Only the relevant preview is refreshed; a generation counter discards stale results and serializes build-preview work to avoid concurrent request storms. In Search & Preview, priority changes regroup existing results locally instead of issuing fresh provider searches. Gallery thumbnail images are cached across these local reorders, and autocomplete filtering is debounced when region enablement changes. Provider system/catalogue caches are retained when unrelated settings such as regions are saved, and cleared only when provider credential values actually change.
