# DS Style Thumbnail Scraper

DS Style Thumbnail Scraper is a Windows desktop application for creating artwork packs for the **DS Style** custom kernel on the EZ-FLASH OMEGA and OMEGA Definitive Edition.

It builds both supported thumbnail formats from Libretro or a local artwork pack, and can create exact-name custom artwork for any file or folder.

## Features

- `120 x 80` title thumbnails for `IMGS`
- `80 x 80` box thumbnails for `IMGS2`
- Libretro and local artwork-pack sources
- Region and artwork selection
- Preview, crop, zoom, and per-entry adjustments
- Exact-name custom artwork for files and folders
- EZ-FLASH-compatible 15-bit BMP output

The Custom Art index supports up to 256 entries in each `CUSTOM` folder because of the cartridge's RAM limits.

## Download and History

- [Download the latest DS Style Thumbnail Scraper release](https://github.com/FrankieT19/ds-style-thumbnail-scraper/releases/latest)
- [Read the complete Thumbnail Scraper changelog](CHANGELOG.md)

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

Read the complete [DS Style User Guide](https://frankiet19.github.io/omega-de-ds-style-kernel/) for artwork setup, custom thumbnails, installation, and troubleshooting.

## Related Repositories

- [DS Style kernel for OMEGA Definitive Edition](https://github.com/FrankieT19/omega-de-ds-style-kernel)
- [DS Style kernel for original OMEGA](https://github.com/FrankieT19/omega-ds-style-kernel)
- [DS Style Customiser](https://github.com/FrankieT19/ds-style-customiser)

## Contributing

Bug reports and focused pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
