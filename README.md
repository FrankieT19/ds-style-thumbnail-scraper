# DS Style Thumbnail Scraper

DS Style Thumbnail Scraper is a Windows desktop application for creating artwork packs for the **DS Style** custom kernel on the EZ-FLASH OMEGA and OMEGA Definitive Edition.

It builds complete Game Boy Advance thumbnail packs from Libretro or a local artwork pack, and creates exact-name artwork for other systems supported by DS Style and Simple. For kernels with mirrored-artwork support, it can reproduce the ROM directory tree under `IMGS` and `IMGS2`, avoiding the flat `CUSTOM` index limit for ROM-matched art.

## DS Style Homepage

Visit the [DS Style homepage](https://frankiet19.github.io/omega-de-ds-style-kernel/project/) for an overview, kernel downloads, tools and example themes.

The [DS Style Manager](https://frankiet19.github.io/omega-de-ds-style-kernel/manager/) provides guided browser installation, a few starting preferences, artwork creation and installed-style management. Full artwork-pack building remains in this desktop Scraper.

## Features

- When multiple artwork matches exist, standard retail releases are prioritized over prototype, beta, demo, hack, mod, translation and other variant releases.
- Optional local-pack-first matching: search detected console folders recursively by title, regardless of alphabet/nested artwork subfolders; found local artwork can override cached and online/hash results.
- The configured local pack is read-only; generated images and caches are written only to the scraper output/cache locations.
- Local-pack lookups stay on the right console: `Nintendo`, `NES`, `Original Nintendo`, `TG16`, `NGPC`, `GBC` and many similar folder names are recognized for NES, Game Boy, Game Boy Color, Game Gear, Master System, TurboGrafx-16/PC Engine and Neo Geo Pocket Color, and artwork from another console's folder is not borrowed when a game has the same title on several systems.
- Cache-first incremental SD scans: reuse completed thumbnails and per-ROM cached source images before online provider lookup
- Optional ROM hash matching toggle in the SD-scan setup: after name searches fail, calculate CRC32, MD5 and SHA-1 and try TheGamesDB then ScreenScraper (slower; off by default)
- Optional automatic fallback toggle in SD-scan setup, also available in the first artwork-download failure prompt, to continue with configured fallback providers for later titles without repeated prompts
- No-Intro filename cleanup for online queries that preserves region tags such as (USA), (Europe), and (Japan) while stripping language, revision, status, and square-bracket dump tags without renaming ROMs or changing output paths
- Responsive region controls: debounce settings saves and Build Pack preview lookups; Search & Preview artwork-priority changes reorder cached results locally without issuing new provider requests

- `120 x 80` title thumbnails for `IMGS`
- `80 x 80` box thumbnails for `IMGS2`
- Libretro and local artwork-pack sources
- System-aware Libretro search with automatic TheGamesDB → ScreenScraper → IGDB fallback when no usable image is found
- Provider credential setup and connection tests for TheGamesDB, ScreenScraper and IGDB, plus live status windows for SD scans and Custom Art builds
- SD library scanning that finds artwork only for installed games
- Try Fallback / Skip Image prompts for unusable SD-scan artwork
- Persistent per-ROM source-image caching and incremental scans that skip existing valid `IMGS` / `IMGS2` thumbnails before searching online providers
- Region and artwork selection
- Preview, crop, zoom, and per-entry adjustments
- Exact-name custom artwork for files and folders
- Mirrored artwork output preserving console/alphabet folders under `IMGS` and `IMGS2`
- Optional `CUSTOM/<extension>.bmp` defaults (for example `gb.bmp` or `nes.bmp`)
- EZ-FLASH-compatible 15-bit BMP output with pure-black transparency key support
- Aspect-preserving, centered box-art fitting for distinctly portrait or landscape source covers, with transparent/black-key margins

The mirrored layout requires a DS Style kernel build that includes the matching mirrored-artwork lookup changes; older kernels continue to use their flat `CUSTOM` lookup. Automatic artwork lookup follows **Libretro → TheGamesDB → ScreenScraper → IGDB** and skips a provider when its credentials are not configured, the console cannot be safely mapped, or the provider returns no fully decodable image. Enter provider credentials under **Settings → Provider Credentials**. TheGamesDB uses an API key; ScreenScraper requires developer ID/password and accepts an optional ScreenScraper user login; IGDB uses Twitch Client ID + Client Secret, and the app obtains its OAuth access token automatically. Each provider has a connection-test control where applicable. Credentials are stored in the local settings JSON file, so keep that file private. When SD scanning encounters an invalid Libretro download, **Try Fallback** advances through the other configured providers, while **Skip Image** continues without that artwork. You can enable automatic fallback before the scan or in the first download-failure prompt to use fallback for later titles without repeated prompts. Long-running SD scans and Custom Art builds display live progress details. The **Custom Art** tab offers two output layouts:

- **Mirror ROM folders (recommended):** artwork follows each ROM's path relative to the SD root selected during Scan SD Card. This output is not limited by the flat `CUSTOM` artwork index. For example, `Game Boy/T/Tetris (World).gb` becomes `IMGS/Game Boy/T/Tetris (World).bmp` and `IMGS2/Game Boy/T/Tetris (World).bmp`.
- **Legacy CUSTOM:** artwork is flattened into `IMGS/CUSTOM` and `IMGS2/CUSTOM`. The kernel's legacy indexed lookup supports up to 256 ordinary custom images per size. Extension defaults such as `gb.bmp` and `nes.bmp` are loaded directly and do not consume an index entry.

To preserve the exact mirror structure, scan the actual SD-card root and keep the ROM folder names unchanged. This keeps intermediate grouping directories as well as console and alphabet folders. Scanning a narrower folder omits parent directories above that selected root (except that selecting a console folder itself is automatically handled). The scraper mirrors the existing ROM tree; it does not move ROM files or invent alphabet folders that do not exist in the ROM layout. Build output is written under `DS Style Thumbnail Scraper output/<timestamp>/`. Copy the generated `IMGS` contents to `SYSTEM/IMGS` and `IMGS2` contents to `SYSTEM/IMGS2`, preserving all subfolders.

For an extension-wide default image, choose **Enter Name...**, enter the extension without a dot (for example `gb`), select its image, and build in either layout. It is written to `IMGS/CUSTOM/gb.bmp` or `IMGS2/CUSTOM/gb.bmp` according to the selected thumbnail size.

Complete full-pack building remains focused on Game Boy Advance; the Custom Art scan builds images only for games that are actually on the SD card.

## Download and History

- [Download the latest DS Style Thumbnail Scraper release](https://github.com/FrankieT19/ds-style-thumbnail-scraper/releases/latest)
- [Changelog](CHANGELOG.md)

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Running From Source

```powershell
.\.venv\Scripts\python "DS Style Thumbnail Scraper.py"
```

## Tests and Building The Executable

Run the mirrored-output, provider fallback and ROM-hash matching, No-Intro cleanup, aspect-fitting, black color-key, retry/skip, cache and SD-scan regression tests from the project folder:

```powershell
python -m unittest discover -s tests -v
python -m py_compile "DS Style Thumbnail Scraper.py" rom_matching.py thumbnail_output_paths.py thumbnail_image_data.py thumbnail_rendering.py ezflash_gba_thumbs.py
```

Build the Windows executable on Windows with Python installed:

```powershell
.\build.ps1
```

## User Guide

Read the [DS Style User Guide](https://frankiet19.github.io/omega-de-ds-style-kernel/) for artwork setup, custom thumbnails, installation, and troubleshooting.

## Related Repositories

- [DS Style kernel for OMEGA Definitive Edition](https://github.com/FrankieT19/omega-de-ds-style-kernel)
- [DS Style kernel for original OMEGA](https://github.com/FrankieT19/omega-ds-style-kernel)
- [DS Style Customiser](https://github.com/FrankieT19/ds-style-customiser)

## Contributing

Bug reports and focused pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
