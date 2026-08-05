# ALBUM

**Automated Library Builder for Unsorted Media**

ALBUM is a minimal pipeline for sorting and renaming photos by shooting date while preserving the original files by default.

Version: `v0.2.0`

Repository: <https://github.com/yoneoka-katsuhiro/ALBUM>

## Purpose

ALBUM copies images from `input_image/` to date-based folders under `output/`. It reads shooting dates from image metadata, applies a unified file name, and leaves all source files untouched unless deletion is explicitly requested.

## Requirements

- macOS
- Python 3.9 or later
- ExifTool

## Installation

For normal use, download the release asset `ALBUM-v0.2.0.zip` from GitHub
Releases. It expands to a clean `ALBUM/` directory:

```bash
cd ALBUM
```

Install ExifTool:

```bash
brew install exiftool
```

Allow the shell wrapper to run:

```bash
chmod +x album.sh
```

## Directory Structure

```text
ALBUM/
├── input_image/
│   └── .gitkeep
├── input_gps/
│   └── .gitkeep
├── input/
│   └── .gitkeep
├── output/
│   └── .gitkeep
├── .gitignore
├── LICENSE
├── VERSION.txt
├── album.py
├── album.sh
└── README.md
```

Photos placed in `input_image/`, legacy `input/`, GPS logs placed in `input_gps/`, and files generated in `output/` are excluded from version control by `.gitignore`. The `.gitkeep` files preserve the empty directory structure in Git.

Copy photos from an SD card into `input_image/` before running ALBUM. Existing `input/` folders from older ALBUM releases are still accepted when `input_image/` is empty.

## Usage

With a known location:

```bash
./album.sh --photographer yoneoka --location yakushima
```

Without a known location:

```bash
./album.sh --photographer yoneoka
```

Delete each input file after its output copy has passed SHA-256 verification:

```bash
./album.sh --photographer yoneoka --location yakushima --remove-input
```

Sort photos and then add missing GPS coordinates from `input_gps/`:

```bash
./album.sh --photographer yoneoka --location yakushima --geotag
```

Only add missing GPS coordinates and write CSV reports:

```bash
./album.sh --geotag-only
```

## Photographer And Location Arguments

`--photographer` is required. `--location` is optional.

Both values may contain only:

```text
A-Z a-z 0-9 - _
```

Spaces, Japanese text, and other symbols are rejected instead of being converted. When `--location` is omitted, `unannotated` is used.

## Output Folder Naming

With a location:

```text
output/YYYYMMDD_location/
```

Without a location:

```text
output/YYYYMMDD_unannotated/
```

Images without a readable date are copied to:

```text
output/unknown_date_location/
output/unknown_date_unannotated/
```

## Output File Naming

With a location:

```text
YYYYMMDD_photographerNNNN_location.ext
```

Without a location:

```text
YYYYMMDD_photographerNNNN_unannotated.ext
```

`NNNN` starts at `0001` for each date, photographer, and location combination. Existing organized files are detected, and new files continue from the next available number.

## Supported Formats

ALBUM supports these extensions, case-insensitively:

```text
jpg jpeg png heic tif tiff dng cr2 cr3 nef arw raf rw2
```

Hidden files, `.DS_Store`, and AppleDouble files beginning with `._` are ignored. Unsupported visible files are reported as `SKIPPED_UNSUPPORTED`.

## Shooting-Date Detection

ExifTool is used with this priority:

1. `DateTimeOriginal`
2. `CreateDate`
3. `FileModifyDate`

If no date can be read, `unknown_date` is used. ALBUM does not convert time zones or edit metadata.

## Optional GPS Geotagging

GPS geotagging is disabled by default. It runs only when `--geotag` or `--geotag-only` is provided.

This feature assumes that the camera clock and the GPS logger or smartphone clock were accurately synchronized at shooting time. If the clocks are offset, ALBUM may write incorrect coordinates. v0.2.0 does not automatically estimate or correct clock drift.

Place GPS logs in `input_gps/`. ALBUM reads these formats:

```text
LOG GPX KML GeoJSON JSON
```

Olympus-style `.LOG` files are read as NMEA GPS logs. GPX and GeoJSON files are read when they contain timestamps. KML files are read only when timestamped points are present; some KML exports preserve the visible route but omit per-point times.

By default, ALBUM matches a photo to GPS points within 300 seconds and interpolates between surrounding points when possible. Change this window with:

```bash
./album.sh --geotag-only --gps-max-gap-seconds 120
```

GPS log timestamps are converted to the Mac's local timezone before comparison with camera timestamps. If the camera was set to a different timezone, provide an explicit offset:

```bash
./album.sh --geotag-only --gps-timezone +09:00
```

When a matching GPS point is found, ALBUM writes decimal latitude and longitude to images that do not already have GPS metadata. Images that already have GPS metadata are not overwritten.

CSV reports are written to `output/`. `input_image/` results are written to:

```text
output/input_image_gps.csv
```

Each organized output folder receives:

```text
output/YYYYMMDD_location/album_gps.csv
```

CSV files use four columns:

```text
photo_name,shot_date,latitude,longitude
```

Blank latitude and longitude fields mean that no coordinate was available for that photo.

## Duplicate Detection

ALBUM uses SHA-256 file hashes. If the same file content already exists anywhere under `output/`, the source file is skipped. If the same content appears multiple times in the active source folder during one run, only the first copy is processed.

## Safety Behavior

By default, ALBUM never modifies, moves, deletes, or overwrites source files in `input_image/` or legacy `input/`. It copies with `shutil.copy2` to preserve metadata where possible, verifies the copied file with SHA-256, and deletes only a newly created incomplete copy if verification fails.

When `--remove-input` is provided, ALBUM deletes only supported source files that were copied to `output/` and passed SHA-256 verification. Duplicate files, unsupported files, hidden files, and files that hit errors are left in place.

When `--geotag` or `--geotag-only` is provided, ALBUM modifies image metadata in place for photos missing GPS coordinates. Back up important originals before using GPS geotagging.

## Progress Output

Long runs print progress messages such as `SCAN_INPUT`, `PROGRESS_READ_INPUT`, `PROGRESS_COPY`, and `PROGRESS_GEOTAG` so that large batches do not appear stalled while ALBUM is reading hashes, metadata, or GPS logs.

## License

The source code is released under the MIT License. Photos placed in
`input_image/` or legacy `input/`, GPS logs placed in `input_gps/`, and
organized copies written to `output/` are not covered by the software license.
