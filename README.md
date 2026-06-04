# DS Style Thumbnail Scraper

DS Style Thumbnail Scraper is a Windows desktop application for creating thumbnail artwork for the **DS Style** custom kernel on the EZ-FLASH OMEGA and OMEGA Definitive Edition.

## Features

- Build complete thumbnail packs without requiring ROM files
- Download box art, title screens, or gameplay screenshots from Libretro
- Convert compatible local artwork collections
- Choose included game regions and regional artwork priority
- Preview, crop, zoom, and reposition artwork
- Set per-game exceptions
- Create case-insensitive exact-name custom artwork for any file or folder
- Generate `120 x 80` title thumbnails for `IMGS`
- Generate `80 x 80` box thumbnails for `IMGS2`

Exact-name custom artwork requires DS Style v6.6 or newer.
Due to the GBA's RAM limitations, each `CUSTOM` folder can contain up to 256 images.

## Requirements

- Windows
- Python 3.10 or newer
- Dependencies from `requirements.txt`
- Internet access when using Libretro

## Running From Source

```powershell
python -m pip install -r requirements.txt
python "DS Style Thumbnail Scraper.py"
```

## Building The Executable

```powershell
.\build.ps1
```

The executable is created at:

```text
dist\DS Style Thumbnail Scraper.exe
```

## Generated Folders

The application creates clearly named folders beside itself:

- `DS Style Thumbnail Scraper Cache` stores downloaded library information.
- `DS Style Thumbnail Scraper output` stores completed thumbnail packs.

These folders are generated at runtime and are not part of the source repository.

## Custom Artwork

Custom artwork uses the exact filename without its final extension, or the exact folder name:

```text
IMGS/CUSTOM/Pokemon Emerald Rogue.bmp
IMGS2/CUSTOM/Pokemon Emerald Rogue.bmp
IMGS/CUSTOM/Game Boy Advance.bmp
```

Files with the same name but different extensions share artwork. For example,
`Game.gba` and `Game.gbc` both use `Game.bmp`. Names otherwise remain exact, so
`Game (1)` and `Game (2)` use separate images.

## Related Repositories

- [DS Style kernel for OMEGA Definitive Edition](https://github.com/FrankieT19/omega-de-ds-style-kernel)
- [DS Style kernel for original OMEGA](https://github.com/FrankieT19/omega-ds-style-kernel)

## Contributing

Bug reports and focused pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
