# Changelog

## v2.0.4 - GB/GBC emulator mode detection

This build includes the v2.0.3 fixes and follow-up improvements.

### New fixes since v2.0.3

- SAV → ESV conversion now sets Jagoomba Color to GB or GBC+SGB based on the matched ROM header.

## v2.0.3 - RTC save compatibility

This build includes the v2.0.2 fixes and follow-up improvements.

### New features since v2.0.2

- Added SAV → ESV support for MBC3 RTC saves by extracting the SRAM payload from the RTC trailer; ESV does not preserve RTC register data.

### New fixes since v2.0.2

- Added a clear conversion warning that RTC data is not preserved between SAV and ESV files.

### Features added through v2.0.2

- **v2.0.3:** Added conversion support for MBC3 RTC save files, retaining SRAM while warning that RTC metadata cannot be stored in ESV.
- **v2.0.2:** Moved the Settings tab to the rightmost position and updated the header subtitle for DS Style Merkin Mix.
- **v2.0.0:** Rebranded the application as DS Style Card Companion and renamed the packaged Windows application.
- **v1.10.14:** Added a clear refresh control for the SAVER listing, matched converter button colors, and named extracted saves after their source archive.
- **v1.10.13:** Enabled the matching conversion button based on the selected file type and placed converted files beside their source.
- **v1.10.12:** Added multi-file selection for conversion and the option to merge SAV files into one selected ESV archive.
- **v1.10.11:** Added the ESV <-> SAV tab to extract Game Boy/Game Boy Color saves from Jagoomba archives and create or update archives from `.sav` files.
- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware provider lookup and fallback, plus Custom Pack builds and mirrored output.
- **v1.10.10:** Added selective transparency, recursive console-aware local-art matching, caching and retry controls, optional ROM hash matching, live progress, and artwork-selection improvements.

### Fixes through v2.0.2

- **v2.0.2:** Preserved access to existing branded output folders for SD scan reports and cached artwork; used a single selected SAV filename as the default ESV name.
- **v2.0.1:** SAV files named after long No-Intro ROM filenames now match GB/GBC ROMs using their cartridge header title and ROM checksum.
- **v2.0.0:** Warned users about possible save-data loss before conversion.
- **v1.10.12:** Moved conversion and ROM indexing off the GUI thread with progress reporting; converted only selected files.
- **v1.10.11:** Extracted current unflushed SRAM when an archive marks a save active; preserved existing extracted saves, rejected unsupported save sizes, reported missing or ambiguous ROM matches, and preserved other saves and savestates when merging.
- **v1.10.10:** Kept local artwork matching scoped to the correct console; improved incremental scans and recovery from failed or invalid artwork downloads; favored standard retail releases and exact ROM matches while preserving cover details and transparency.
- **v1.10.10:** Hardened standalone GBA utilities for mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; safely handled malformed settings, scan reports, and provider caches.

These changes and fixes were completed with the assistance of AI.

## v2.0.2 - Branding compatibility and interface updates

This build includes the v2.0.1 fixes and follow-up improvements.

### New features since v2.0.1

- Moved the Settings tab to the rightmost position and updated the header subtitle for DS Style Merkin Mix.

### New fixes since v2.0.1

- Defaulted a single selected SAV conversion to an ESV filename based on the SAV name.
- Kept SD scan reports and artwork reuse compatible with existing DS Style Thumbnail Scraper output folders.

### Features added through v2.0.1

- **v2.0.2:** Moved the Settings tab to the rightmost position and updated the header subtitle for DS Style Merkin Mix.
- **v2.0.0:** Rebranded the application as DS Style Card Companion and renamed the packaged Windows application.
- **v1.10.14:** Added a clear refresh control for the SAVER listing, matched converter button colors, and named extracted saves after their source archive.
- **v1.10.13:** Enabled the matching conversion button based on the selected file type and placed converted files beside their source.
- **v1.10.12:** Added multi-file selection for conversion and the option to merge SAV files into one selected ESV archive.
- **v1.10.11:** Added the ESV <-> SAV tab to extract Game Boy/Game Boy Color saves from Jagoomba archives and create or update archives from `.sav` files.
- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware provider lookup and fallback, plus Custom Pack builds and mirrored output.
- **v1.10.10:** Added selective transparency, recursive console-aware local-art matching, caching and retry controls, optional ROM hash matching, live progress, and artwork-selection improvements.

### Fixes through v2.0.1

- **v2.0.2:** Preserved access to existing branded output folders for SD scan reports and cached artwork; used a single selected SAV filename as the default ESV name.
- **v2.0.1:** SAV files named after long No-Intro ROM filenames now match GB/GBC ROMs using their cartridge header title and ROM checksum.
- **v2.0.0:** Warned users about possible save-data loss before conversion.
- **v1.10.12:** Moved conversion and ROM indexing off the GUI thread with progress reporting; converted only selected files.
- **v1.10.11:** Extracted current unflushed SRAM when an archive marks a save active; preserved existing extracted saves, rejected unsupported save sizes, reported missing or ambiguous ROM matches, and preserved other saves and savestates when merging.
- **v1.10.10:** Kept local artwork matching scoped to the correct console; improved incremental scans and recovery from failed or invalid artwork downloads; favored standard retail releases and exact ROM matches while preserving cover details and transparency.
- **v1.10.10:** Hardened standalone GBA utilities for mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; safely handled malformed settings, scan reports, and provider caches.

These changes and fixes were completed with the assistance of AI.

## v2.0.1 - GB/GBC save filename matching

This build includes the v2.0.0 fixes and follow-up improvements.

### New features since v2.0.0

- None.

### New fixes since v2.0.0

- SAV files named after long No-Intro ROM filenames now match GB/GBC ROMs using their cartridge header title and ROM checksum.

### Features added through v2.0.0

- **v2.0.0:** Rebranded the application as DS Style Card Companion and renamed the packaged Windows application.
- **v1.10.14:** Added a clear refresh control for the SAVER listing, matched converter button colors, and named extracted saves after their source archive.
- **v1.10.13:** Enabled the matching conversion button based on the selected file type and placed converted files beside their source.
- **v1.10.12:** Added multi-file selection for conversion and the option to merge SAV files into one selected ESV archive.
- **v1.10.11:** Added the ESV <-> SAV tab to extract Game Boy/Game Boy Color saves from Jagoomba archives and create or update archives from `.sav` files.
- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware provider lookup and fallback, plus Custom Pack builds and mirrored output.
- **v1.10.10:** Added selective transparency, recursive console-aware local-art matching, caching and retry controls, optional ROM hash matching, live progress, and artwork-selection improvements.

### Fixes through v2.0.0

- **v2.0.0:** Warned users about possible save-data loss before conversion.
- **v1.10.12:** Moved conversion and ROM indexing off the GUI thread with progress reporting; converted only selected files.
- **v1.10.11:** Extracted current unflushed SRAM when an archive marks a save active; preserved existing extracted saves, rejected unsupported save sizes, reported missing or ambiguous ROM matches, and preserved other saves and savestates when merging.
- **v1.10.10:** Kept local artwork matching scoped to the correct console; improved incremental scans and recovery from failed or invalid artwork downloads; favored standard retail releases and exact ROM matches while preserving cover details and transparency.
- **v1.10.10:** Hardened standalone GBA utilities for mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; safely handled malformed settings, scan reports, and provider caches.

These changes and fixes were completed with the assistance of AI.

## v2.0.0 - DS Style Card Companion

This build includes the v1.10.14 fixes and follow-up improvements.

### New features since v1.10.14

- Rebranded the application as **DS Style Card Companion** and updated the build number to v2.0.0.
- Renamed the packaged Windows application to `DS Style Card Companion.exe`.

### New fixes since v1.10.14

- None.

### Features added through v1.10.14

- **v2.0.0:** Rebranded the application as DS Style Card Companion and renamed the packaged Windows application.
- **v1.10.14:** Added a clear refresh control for the SAVER listing, matched converter button colors, and named extracted saves after their source archive.
- **v1.10.13:** Enabled the matching conversion button based on the selected file type and placed converted files beside their source.
- **v1.10.12:** Added multi-file selection for conversion and the option to merge SAV files into one selected ESV archive.
- **v1.10.11:** Added the ESV <-> SAV tab to extract Game Boy/Game Boy Color saves from Jagoomba archives and create or update archives from `.sav` files.
- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware Libretro, TheGamesDB, ScreenScraper, and IGDB lookup and automatic fallback.
- **v1.10.10:** Added Custom Pack builds for all systems or a selected system, with mirrored ROM-folder output under `IMGS`/`IMGS2`, flat `CUSTOM` output, and extension defaults.
- **v1.10.10:** Added selective transparency markers for compatible DS Style kernels, recursive console-aware local artwork matching, and an option to prioritize read-only local packs.
- **v1.10.10:** Added incremental artwork caching, retry/skip options, optional CRC32/MD5/SHA-1 matching, improved online filename cleanup, provider totals, and live progress for scans and artwork builds.

### Fixes through v1.10.14

- **v1.10.14:** Extracted `.sav` files using their source `.esv` name, with game titles appended for archives containing multiple saves.
- **v1.10.13:** Warned users about possible save-data loss before conversion.
- **v1.10.12:** Moved conversion and ROM indexing off the GUI thread with progress reporting; converted only selected files.
- **v1.10.11:** Extracted current unflushed SRAM when an archive marks a save active; preserved existing extracted saves, rejected unsupported save sizes, reported missing or ambiguous ROM matches, and preserved other saves and savestates when merging.
- **v1.10.10:** Kept local artwork matching scoped to the correct console; improved incremental scans and recovery from failed or invalid artwork downloads; favored standard retail releases and exact ROM matches while preserving cover details and transparency.
- **v1.10.10:** Hardened standalone GBA utilities for mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; safely handled malformed settings, scan reports, and provider caches.

These changes and fixes were completed with the assistance of AI.

## v1.10.14 - ESV/SAV scan and filename improvements

This build includes the v1.10.13 fixes and follow-up improvements.

### New features since v1.10.13

- Renamed the **Scan** control to **Refresh Scan** to make clear that it reloads the current `SYSTEM/SAVER` file listing.
- Matched the colors of the ESV → SAV and SAV → ESV conversion buttons.

### New fixes since v1.10.13

- Extracted `.sav` files now use their source `.esv` filename; archives with multiple saves append each game title to keep the filenames distinct.

### Features added through v1.10.13

- **v1.10.14:** Added a clear refresh control for the SAVER listing, matched converter button colors, and named extracted saves after their source archive.
- **v1.10.13:** Enabled the matching conversion button based on the selected file type and placed converted files beside their source.
- **v1.10.12:** Added multi-file selection for conversion and the option to merge SAV files into one selected ESV archive.
- **v1.10.11:** Added the ESV <-> SAV tab to extract Game Boy/Game Boy Color saves from Jagoomba archives and create or update archives from `.sav` files.
- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware Libretro, TheGamesDB, ScreenScraper, and IGDB lookup and automatic fallback.
- **v1.10.10:** Added Custom Pack builds for all systems or a selected system, with mirrored ROM-folder output under `IMGS`/`IMGS2`, flat `CUSTOM` output, and extension defaults.
- **v1.10.10:** Added selective transparency markers for compatible DS Style kernels, recursive console-aware local artwork matching, and an option to prioritize read-only local packs.
- **v1.10.10:** Added incremental artwork caching, retry/skip options, optional CRC32/MD5/SHA-1 matching, improved online filename cleanup, provider totals, and live progress for scans and artwork builds.

### Fixes through v1.10.13

- **v1.10.13:** Warned users about possible save-data loss before conversion.
- **v1.10.12:** Moved conversion and ROM indexing off the GUI thread with progress reporting; converted only selected files.
- **v1.10.11:** Extracted current unflushed SRAM when an archive marks a save active; preserved existing extracted saves, rejected unsupported save sizes, reported missing or ambiguous ROM matches, and preserved other saves and savestates when merging.
- **v1.10.10:** Kept local artwork matching scoped to the correct console; improved incremental scans and recovery from failed or invalid artwork downloads; favored standard retail releases and exact ROM matches while preserving cover details and transparency.
- **v1.10.10:** Hardened standalone GBA utilities for mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; safely handled malformed settings, scan reports, and provider caches.

These changes and fixes were completed with the assistance of AI.

## v1.10.13 - Safer ESV/SAV conversion

This build includes the v1.10.12 fixes and follow-up improvements.

### New features since v1.10.12

- Conversion buttons now activate for the selected file type: ESV → SAV for ESV selections and SAV → ESV for SAV selections.
- Converted files are placed beside their selected source files instead of in a separate output folder.

### New fixes since v1.10.12

- Added a confirmation warning before conversion explaining that save data could be lost and recommending backups.

### Features added through v1.10.12

- **v1.10.13:** Enabled the matching conversion button based on the selected file type and placed converted files beside their source.
- **v1.10.12:** Added multi-file selection for conversion and the option to merge SAV files into one selected ESV archive.
- **v1.10.11:** Added the ESV <-> SAV tab to extract Game Boy/Game Boy Color saves from Jagoomba archives and create or update archives from `.sav` files.
- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware Libretro, TheGamesDB, ScreenScraper, and IGDB lookup and automatic fallback.
- **v1.10.10:** Added Custom Pack builds for all systems or a selected system, with mirrored ROM-folder output under `IMGS`/`IMGS2`, flat `CUSTOM` output, and extension defaults.
- **v1.10.10:** Added selective transparency markers for compatible DS Style kernels, recursive console-aware local artwork matching, and an option to prioritize read-only local packs.
- **v1.10.10:** Added incremental artwork caching, retry/skip options, optional CRC32/MD5/SHA-1 matching, improved online filename cleanup, provider totals, and live progress for scans and artwork builds.

### Fixes through v1.10.12

- **v1.10.13:** Warned users about possible save-data loss before conversion.
- **v1.10.12:** Moved conversion and ROM indexing off the GUI thread with progress reporting; converted only selected files.
- **v1.10.11:** Extracted current unflushed SRAM when an archive marks a save active; preserved existing extracted saves, rejected unsupported save sizes, reported missing or ambiguous ROM matches, and preserved other saves and savestates when merging.
- **v1.10.10:** Kept local artwork matching scoped to the correct console; improved incremental scans and recovery from failed or invalid artwork downloads; favored standard retail releases and exact ROM matches while preserving cover details and transparency.
- **v1.10.10:** Hardened standalone GBA utilities for mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; safely handled malformed settings, scan reports, and provider caches.

These changes and fixes were completed with the assistance of AI.

## v1.10.12 - Responsive ESV/SAV conversion

This build includes the v1.10.11 fixes and follow-up improvements.

### New features since v1.10.11

- The SAV → ESV workflow can merge into one selected ESV archive; selecting no ESV lets you create a new archive.
- The SAVER list supports selecting multiple files for conversion.

### New fixes since v1.10.11

- Moved ESV/SAV conversion and GB/GBC ROM indexing off the GUI thread, with a progress window that reports conversion and scan progress.
- Conversions now process only the selected ESV or SAV files instead of every matching file in `SYSTEM/SAVER`.

### Features added through v1.10.11

- **v1.10.11:** Added the ESV <-> SAV tab to extract Game Boy/Game Boy Color saves from Jagoomba archives and create or update archives from `.sav` files.
- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware Libretro, TheGamesDB, ScreenScraper, and IGDB lookup and automatic fallback.
- **v1.10.10:** Added Custom Pack builds for all systems or a selected system, with mirrored ROM-folder output under `IMGS`/`IMGS2`, flat `CUSTOM` output, and extension defaults.
- **v1.10.10:** Added selective transparency markers for compatible DS Style kernels, recursive console-aware local artwork matching, and an option to prioritize read-only local packs; matching local images build directly without copying or modifying source files.
- **v1.10.10:** Added incremental artwork caching and retry/skip options, optional ROM matching by CRC32, MD5, and SHA-1, region-preserving online filename cleanup, provider totals with matched filenames for small result sets, live progress for scans and artwork builds, and updated compatibility guidance through DS Style v7.4.

### Fixes through v1.10.11

- **v1.10.11:** Extracted current unflushed SRAM when an archive marks a save active; preserved existing extracted saves, rejected unsupported save sizes, reported missing or ambiguous ROM matches, and preserved other saves and savestates when merging.
- **v1.10.10:** Kept local artwork matching scoped to the correct console; improved incremental scans and recovery from failed or invalid artwork downloads; favored standard retail releases and exact ROM matches while preserving cover details and transparency.
- **v1.10.10:** Hardened standalone GBA utilities for mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; safely handled malformed settings, scan reports, and provider caches.

These changes and fixes were completed with the assistance of AI.

## v1.10.11 - Jagoomba Color ESV/SAV conversion

Only v1.10.10 was published between the fork's creation and this release.

### New features in v1.10.11

- Added the **ESV <-> SAV** tab to scan `SYSTEM/SAVER` for Jagoomba Color `.esv` archives and `.sav` files.
- Extracts every Game Boy/Game Boy Color save in an archive into a separate `Converted SAV` folder.
- Builds or merges emulator-compatible ESV archives from `.sav` files matched to GB/GBC ROM titles and checksums on the SD card; the output name can be selected and defaults to the detected emulator plugin.

### Fixes in v1.10.11

- Extracts the current unflushed SRAM bytes when a Jagoomba archive marks a save as active.
- Leaves existing extracted `.sav` files untouched, reports missing or ambiguous ROM matches, and validates save sizes before writing.
- Merging into an existing ESV keeps its other game saves and savestates.

### New features from previous releases since the fork (v1.10.10)

- **v1.10.10:** Expanded artwork search and SD-card scanning beyond GBA, with system-aware Libretro, TheGamesDB, ScreenScraper, and IGDB lookup and automatic fallback.
- **v1.10.10:** Added Custom Pack builds for all systems or a selected system, with mirrored ROM-folder output under `IMGS`/`IMGS2`, flat `CUSTOM` output, and extension defaults.
- **v1.10.10:** Added selective transparency markers for compatible DS Style kernels, recursive console-aware local artwork matching, and an option to prioritize read-only local packs; matching local images build directly without copying or modifying source files.
- **v1.10.10:** Added incremental artwork caching and retry/skip options, optional ROM matching by CRC32, MD5, and SHA-1, region-preserving online filename cleanup, and provider totals with matched filenames for small result sets.
- **v1.10.10:** Added live progress for scans and artwork builds, and updated compatibility guidance through DS Style v7.4.

### Fixes from previous releases since the fork (v1.10.10)

- **v1.10.10:** Kept local artwork matching scoped to the correct console, preventing same-title games from borrowing another system's art; local source packs remain unchanged.
- **v1.10.10:** Improved incremental scans to reuse valid thumbnails and cached source images, and made failed or invalid artwork downloads recoverable through retry, fallback, or skip.
- **v1.10.10:** Improved artwork selection to prefer standard retail releases and exact ROM matches, while preserving cover details and transparency when fitting non-square artwork.
- **v1.10.10:** Hardened standalone GBA utilities to handle mixed-case `.GBA` filenames, invalid dimensions and limits, and unreadable ROMs; malformed settings, scan reports, and provider caches are handled safely.

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
