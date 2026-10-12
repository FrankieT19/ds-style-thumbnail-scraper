# Changelog

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
