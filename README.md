# DS Style Thumbnail Scraper

DS Style Thumbnail Scraper is a Windows desktop application for creating artwork packs for the **DS Style** custom kernel on the EZ-FLASH OMEGA and OMEGA Definitive Edition.

It builds complete Game Boy Advance thumbnail packs from Libretro or a local artwork pack, and creates exact-name CUSTOM artwork for other systems supported by DS Style and Simple.

## DS Style Homepage

Visit the [DS Style homepage](https://frankiet19.github.io/omega-de-ds-style-kernel/project/) for an overview, kernel downloads, tools and example themes.

The [DS Style Manager (Beta)](https://frankiet19.github.io/omega-de-ds-style-kernel/manager/) provides guided browser installation, a few starting preferences, artwork creation and installed-style management. Full artwork-pack building remains in this desktop Scraper.

## Features

- `120 x 80` title thumbnails for `IMGS`
- `80 x 80` box thumbnails for `IMGS2`
- Libretro and local artwork-pack sources
- System-aware Libretro search for supported consoles
- SD library scanning that finds artwork only for installed games
- Region and artwork selection
- Preview, crop, zoom, and per-entry adjustments
- Exact-name custom artwork for files and folders
- EZ-FLASH-compatible 15-bit BMP output

The Custom Art index supports up to 256 entries in each `CUSTOM` folder because of the cartridge's RAM limits.

Complete pack building remains focused on Game Boy Advance. Artwork for other systems is written to `IMGS/CUSTOM` and `IMGS2/CUSTOM`, keeping the result limited to games that are actually on the SD card.

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

## Building The Executable

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
