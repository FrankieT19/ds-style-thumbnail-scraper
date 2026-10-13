# Changelog

## v1.10.5 - Console-aware local artwork folders

- Fixed local-pack lookups returning artwork from the wrong console when several consoles share a game title, for example Game Boy box art being used for the NES version of the same game while a matching image existed in a `Nintendo` folder.
- Local-pack console folders are now recognized under many more common names for NES (`Nintendo`, `Original Nintendo`, `Famicom`, `FC`, ...), Game Boy, Game Boy Color, Game Gear, Master System, TurboGrafx-16/PC Engine (`TG16`, `PCE`, ...) and Neo Geo Pocket Color (`NGPC`, ...), including libretro-thumbnails, LaunchBox, ES-DE/Batocera and OnionOS style names.
- The deepest console-specific folder wins, so `Nintendo/Game Boy/...` is Game Boy; a bare `Nintendo` folder is only treated as NES when nothing more specific is in the same path, and a publisher folder such as `GBA/Box Art/Nintendo/` no longer changes which console owns the image.
- When a console has no folder of its own, artwork from folders that clearly belong to another console (including unsupported ones such as SNES, Genesis and Arcade) is no longer borrowed; artwork in unlabeled folders is still used, and packs with no console folders keep the original whole-pack matching.
- Names such as `Game Boy (Color)` are read as Game Boy Color rather than Game Boy. Neo Geo Pocket and Neo Geo Pocket Color folders may serve either console because `.ngc` files are scanned as Neo Geo Pocket.
- Faster console scoping on large media collections, and added regression tests for every alias, nested folders, publisher folders and cross-console protection.

## v1.10.4 - Local-pack-first artwork lookup
- Added a Settings toggle that makes matching local-pack artwork take priority over existing cached source images, selected online providers, and optional ROM hash lookup. The option is off by default.
- Local packs are recursively name-matched inside detected console folders, independent of alphabet/nested folder layout; if no console folder is identifiable, the original whole-pack matching behavior remains.
- Local packs are read-only sources. All generated thumbnails and source-image caches stay in the scraper output/cache locations.
- Added regression coverage for console-aware nested matching, local source read-only behavior, and local-pack priority over cached/hash/provider paths.

## v1.10.3 - Automatic fallback toggle for SD scans

- Added an SD-scan setup option to automatically try configured fallback providers when a Libretro artwork download fails, without prompting for each affected title.
- Added the same opt-in control to the first “Artwork Image Unavailable” prompt; enabling it applies to all later titles in that scan while preserving the user's choice to fallback or skip the current image.
- The existing optional ROM hash-matching toggle remains alongside the new automatic-fallback option. When enabled, hash matching remains the final recovery attempt after name-based fallback fails.
- Added offline regression tests for pre-enabled automatic fallback and enabling it from the first per-image prompt.


## v1.10.2 - Retail release artwork priority

- Rank the standard retail release ahead of alpha, beta, prototype, demo, test/debug, unreleased, hack, mod, fan-translation, randomizer, bootleg and other non-retail variants when several candidates match a title.
- Apply variant ranking before result limits in Libretro, TheGamesDB, ScreenScraper and IGDB searches, so a non-retail result returned first by a provider does not win just because only one result was requested.
- Apply the same retail-first preference to local art-pack and filename-index matching while keeping variants available as fallback choices when no retail artwork exists.
- Preserve No-Intro region tags in provider search queries while cleaning language, revision/version, status, and dump tags.
- Prefer explicit ROM CRC/MD5/SHA-1 hash-match results above title-only matches because the checksum match identifies the exact ROM release.
- Added offline regression tests for variant classification, retail-first selection, retained region tags, and hash-match priority.


## v1.10.1 - Responsive region controls and previews

- Debounced settings writes for Game regions to build and Artwork priority controls, avoiding repeated synchronous serialization while the user clicks rapidly.
- Prevented Artwork priority edits from triggering duplicate online searches across both tabs. Build Pack preview refreshes are debounced, run in a single background worker, discard stale results, and show a visible indeterminate progress bar/status while providers are queried.
- Search & Preview priority edits reorder already-fetched results locally instead of running another provider query; local gallery thumbs are reused from cache, and suggestion filtering is debounced on enable/disable.
- Provider system/catalogue caches are invalidated only when saved provider credentials actually change, not on ordinary region or UI preference saves.
- Added regression tests for region-scope isolation, debounced actions, preview coalescing, and provider-cache preservation.


## v1.10.0 - Optional ROM hash matching and No-Intro query cleanup

- Added a pre-scan checkbox for optional ROM hash matching. It is off by default and only hashes ROM contents after cached artwork, existing thumbnails, and all name-based provider searches fail.
- Computes CRC32, MD5, SHA-1 and file size in one streaming read. Hash-based lookup tries TheGamesDB and then ScreenScraper using the detected console/platform; Libretro and IGDB do not expose a direct ROM-file hash artwork lookup.
- Preserves common No-Intro region tags in online search queries while cleaning language, revision/version and square-bracket dump/status tags; original ROM filenames, relative output paths and cache identities are unchanged.
- Added offline tests for filename cleanup, streaming hashes, provider hash parameters, fallback order and the pre-scan toggle.


## v1.9.2 - Selective transparent thumbnail marker

- Mark only BMP outputs that contain intentional transparent canvas pixels with `DST1` in the reserved BMP header bytes expected by compatible kernel builds.
- Keep opaque GBA and legacy CUSTOM BMP outputs unmarked, preserving their current color-key behavior.
- Add regression coverage for marked padded artwork and unmarked opaque images.


## v1.9.1

- Made the SD-card scan strictly cache-first: already-built, valid IMGS/IMGS2 thumbnails are detected before provider matching; existing custom-entry image files and a durable per-ROM source-image cache are checked before Libretro, TheGamesDB, ScreenScraper or IGDB are queried.
- Added a per-ROM source-image cache keyed by console, selected artwork type and ROM-relative path. Successful Libretro/fallback results are written to this cache, so later scans can reuse the exact image without re-contacting providers even when a provider previously had no Libretro match.
- Deferred Libretro artwork-index matching until after the output/cache checks, avoiding unnecessary index requests for games whose artwork is already present.
- Added regression tests proving both Libretro matches and fallback-provider matches are served from per-ROM cache on subsequent scans, and that existing final thumbnails skip provider lookup entirely.

## v1.9.0

- Expanded automatic artwork fallback to a strict provider order: Libretro → TheGamesDB → ScreenScraper → IGDB. Providers are skipped when credentials are absent, system/platform matching is unavailable, or no fully decodable image is returned.
- Wired ScreenScraper developer credentials into system-aware search. ScreenScraper user login is optional; if entered, username and password must be supplied together. The scraper resolves each console to a ScreenScraper system ID before searching.
- Replaced the IGDB manual access-token field with Twitch Client ID + Client Secret. The scraper requests and caches OAuth app tokens, resolves IGDB platform IDs per console, and filters each game query to that platform. Existing manually saved access tokens remain a temporary compatibility fallback.
- Changed the invalid/incomplete SD-scan image prompt from Retry Download to Try Fallback. Selecting it tries TheGamesDB, ScreenScraper, then IGDB, and caches the first valid result; Skip Image remains available.
- Added provider-specific credential test actions and links to the credential/API pages for IGDB and ScreenScraper, alongside the existing TheGamesDB key test.
- Added offline regression coverage for fallback order, platform-aware IGDB lookup, OAuth token exchange, ScreenScraper system lookup, invalid media rejection, and Try Fallback behavior.

## v1.8.0

- Added a dedicated TheGamesDB API-key control under Settings → Provider Credentials, including masked entry, Show/Hide, a link to request an API key, and a live Test key action.
- Added a responsive status window to SD scans, showing folder enumeration, ROM matching, existing-thumbnail checks, provider fallback, cache work and download progress with elapsed time and current item details.
- Moved Build Custom Art output generation to a background worker and added per-thumbnail progress, elapsed time and destination details so the application remains responsive during large builds.
- Added regression tests for TheGamesDB key verification, progress callback dispatch and SD enumeration status updates.

## v1.7.0

- Added automatic TheGamesDB artwork fallback when Libretro search has no usable match, using the selected console's platform ID to avoid cross-system results.
- TheGamesDB fallback uses the API key configured under Settings → Provider Credentials; platform metadata is cached for 30 days.
- For 80×80 box-art output, distinctly portrait or landscape source art is scaled proportionally, centered, and contained in the square canvas instead of being cropped to fill it.
- Empty canvas pixels export as pure black (RGB555 zero), the DS Style transparency color key. Visible source pixels that would quantize to black are lifted to RGB555 #080808 so genuine black detail remains visible.
- Added regression tests for API fallback/platform filtering, SD-scan fallback, aspect-preserving artwork fit, and black color-key transparency.

## v1.6.2

- Added Retry Download / Skip Image prompts when an artwork request fails or returns invalid image data.
- Added a persistent source-image cache keyed by console, artwork type and provider filename, avoiding repeat downloads across scans.
- Skip valid mirrored thumbnails already present under SD `SYSTEM/IMGS`, `SYSTEM/IMGS2`, `IMGS` or `IMGS2`, as well as prior timestamped scraper output folders.
- Reuse valid saved custom-art cache images from earlier versions when another thumbnail size is needed.
- Added regression tests for retry, skip, persistent-cache hits, existing artwork and corrupt output thumbnails.

## v1.6.1

- Fixed Custom Art SD scans aborting when an artwork URL returned non-image, truncated, or otherwise invalid data.
- Validate downloaded image payloads before caching them; invalid responses are reported in SD Scan Results and skipped so the rest of the library can finish scanning.
- Added regression tests for HTML error responses, Git LFS pointer text, empty payloads, truncated images, and valid image bytes.

## v1.6

- Added mirrored artwork output that preserves each ROM's relative console/alphabet folder path under `IMGS` and `IMGS2`.
- Removed the 256-entry scan-time cap; mirror output can include large libraries and duplicate game names in separate folders.
- Kept a Legacy CUSTOM output option with the 256-image limit enforced only for flat, indexed custom artwork.
- Added support/documentation for extension defaults such as `IMGS/CUSTOM/gb.bmp` and `IMGS2/CUSTOM/nes.bmp`.
- Persisted mirror/legacy output selection and added path-safety tests for mirrored output.

## v1.5

- Added Libretro artwork search for the additional systems supported by DS Style and Simple.
- Added SD library scanning to match only games already present on the card.
- Added automatic CUSTOM output for non-GBA systems while preserving the existing GBA full-pack workflow.
- Enforced the 256-image limit independently for wide and square CUSTOM artwork.
- Updated compatibility information for DS Style v7.4.

## v1.4

- Improved scaling and window sizing on high-resolution displays and smaller desktops.
- Kept the Custom Art build command visible when vertical space is limited.
- Updated compatibility information for DS Style v7.2.

## v1.3

- Added custom thumbnail support for folders and all files.
- Removed the need to edit ROM headers when assigning custom artwork.
- Improved DS Style kernel integration.

## v1.2

- Improved the artwork search algorithm.
- Added general optimisations.

## v1.1

- Improved homebrew artwork handling.

## v1.0

- Initial release.
