# ALBUM

**Automated Library Builder for Unsorted Media**

ALBUM is a minimal pipeline for sorting and renaming photos by shooting date while preserving the original files by default.

Version: `v0.1.1`

Repository: <https://github.com/yoneoka-katsuhiro/ALBUM>

## Purpose

ALBUM copies images from `input/` to date-based folders under `output/`. It reads shooting dates from image metadata, applies a unified file name, and leaves all source files untouched unless deletion is explicitly requested.

## Requirements

- macOS
- Python 3.9 or later
- ExifTool

## Installation

For normal use, download the release asset `ALBUM-v0.1.1.zip` from GitHub
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

Photos placed in `input/` and files generated in `output/` are excluded from version control by `.gitignore`. The `.gitkeep` files preserve the empty directory structure in Git.

Copy photos from an SD card into `input/` before running ALBUM.

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

## Duplicate Detection

ALBUM uses SHA-256 file hashes. If the same file content already exists anywhere under `output/`, the input file is skipped. If the same content appears multiple times in `input/` during one run, only the first copy is processed.

## Safety Behavior

By default, ALBUM never modifies, moves, deletes, or overwrites files in `input/`. It copies with `shutil.copy2` to preserve metadata where possible, verifies the copied file with SHA-256, and deletes only a newly created incomplete copy if verification fails.

When `--remove-input` is provided, ALBUM deletes only supported input files that were copied to `output/` and passed SHA-256 verification. Duplicate files, unsupported files, hidden files, and files that hit errors are left in `input/`.

## License

The source code is released under the MIT License. Photos placed in `input/`
and organized copies written to `output/` are not covered by the software
license.
