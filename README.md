# EZ Flash Omega DE GBA Thumbnail Maker

This tool scans `.gba` files, reads each ROM's internal 4-character game code, downloads matching Game Boy Advance box art from the public Libretro thumbnail set, and writes EZ Flash Omega/Omega DE compatible thumbnail BMPs.

Generated box art is standardized to `80x80`, scaled to fill the square, left edge preserved, extra pixels cut from the right, and any top/bottom crop centered.

The official EZ Flash thumbnail pack uses:

- `120x80` pixels
- 16-bit BMP, top-down rows, GBA BGR555 color
- `IMGS/<first game-code char>/<second game-code char>/<GAMECODE>.bmp`

Example: a ROM with header code `A22J` becomes `IMGS/A/2/A22J.bmp`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

If `python` opens the Microsoft Store, install Python for Windows first or disable the Store execution alias in Windows settings.

## Use

After building the `.exe`, you can place it in a folder with your `.gba` ROMs and double-click it. It scans that folder and every folder inside it, and writes thumbnails to an `IMGS` folder beside the executable.

```powershell
.\.venv\Scripts\python ezflash_gba_thumbs.py "D:\GBA ROMs" --output "E:\IMGS"
```

You can also run the Python script without arguments from this folder to use the same drop-in behavior.

## Full Library Builder

`EZFlashGBAFullBoxArtThumbs.exe` does not need ROMs. It downloads the Libretro No-Intro GBA metadata mirror, uses each game's serial/header code, matches the release to Libretro box art, and creates a complete `IMGS` folder beside the executable.

This can take a while because it downloads thousands of images. If you stop it and run it again, existing thumbnails are skipped unless you use `--overwrite`.

## Local Art Pack Converter

`EZFlashGBALocalBoxArtPackThumbs.exe` converts an unzipped local art pack into the same EZ Flash thumbnail format. Put the executable beside the extracted pack folder, or pass the folder path on the command line. Art outside `Europe` folders is preferred; a `Europe` folder is used only as a fallback when no primary match exists.

## DS Style Thumbnail Scraper

`DS Style Thumbnail Scraper.exe` is a styled desktop app for building thumbnail packs from Libretro, local packs, IGDB, TheGamesDB, or ScreenScraper. Libretro and local packs work without accounts; the other providers require their own API credentials. It supports `120x80 -> IMGS` and `80x80 -> IMGS2`, region filters, preview search, multiple provider result choices, crop/zoom controls, per-game exceptions, local-image overrides, and run-by-run output folders under `DS Style Thumbnail Scraper output`.

DS Style Thumbnail Scraper v1.3 is made for DS Style v6.7 or newer. Older DS Style kernels do not use the `CUSTOM` exact-name artwork folders.

Use `--overwrite` to replace existing thumbnails.

## Custom Art Overrides

DS Style can also load exact-name custom thumbnails without editing ROM headers.

The desktop app's `Custom Art` tab creates:

- `IMGS/CUSTOM/<file or folder name>.bmp` for title thumbnails
- `IMGS2/CUSTOM/<file or folder name>.bmp` for box thumbnails

Example:

- File: `Pokemon Emerald Rogue.gba`
- Title thumbnail: `IMGS/CUSTOM/Pokemon Emerald Rogue.bmp`
- Box thumbnail: `IMGS2/CUSTOM/Pokemon Emerald Rogue.bmp`

Folder example:

- Folder: `Game Boy Advance`
- Title thumbnail: `IMGS/CUSTOM/Game Boy Advance.bmp`
- Box thumbnail: `IMGS2/CUSTOM/Game Boy Advance.bmp`

These files are checked before the normal header-code thumbnail, so they can override artwork for ROM hacks that still use their base game's internal header. If there is no matching custom file, DS Style falls back to the usual `IMGS/A/2/A22J.bmp` layout where possible. This is useful for ROM hacks, homebrew, translations, prototypes, folders, emulated games, or anything else that needs exact-name artwork.

Use `--width 120 --height 80 --fit cover` if you want the official screenshot-sized canvas. Use `--fit contain` if you want padding instead of cropping. Use `--width 0` to return to variable-width art scaled only by height.

Windows image viewers may show the generated BMP colors incorrectly. That is expected: EZ Flash thumbnail BMPs use the GBA's 15-bit color channel order inside a BMP container.

## Notes

- The tool does not download games. It only reads ROM headers from files you already have.
- Matching depends mostly on the ROM filename, so clean No-Intro-style filenames work best.
- If a game is missed, rename the ROM file closer to its normal release title and run again, or use another matching source later.
- The first run caches the online box-art index in `DS Style Thumbnail Scraper Cache/libretro_gba_boxarts.json`; use `--refresh-index` to update it.
