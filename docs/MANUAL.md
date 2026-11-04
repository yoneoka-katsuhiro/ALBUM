# ALBUM user manual — 0.3.0

[日本語](MANUAL-ja.md) · [Overview and downloads](../README.md)

## 1. Prepare a working folder

Extract the complete release package into a writable folder such as Documents. The executable, `_internal`, and `exiftool` directories must stay together. Put photographs in `input_image` and optional GPS logs in `input_gps`. ALBUM creates `output` if necessary. Keep an independent backup of important photographs.

The default working folder is beside the executable, or beside `album.py` when running the source. To store data elsewhere, pass `--project-dir "/path/to/my photos"`. Quote paths containing spaces. This folder contains the same three subfolders. Symbolic links for these data folders, and linked files within them, are not supported.

On macOS, run `./album` from Terminal. On Windows, run `.\album.exe` from PowerShell. The examples below use the macOS command; substitute the Windows command when appropriate. For source use, substitute `python album.py` and install ExifTool separately.

## 2. Organize photographs

```bash
./album --photographer yoneoka --location yakushima
```

`--photographer` is required for copying. `--location` defaults to `unannotated`. Both accept only ASCII letters, digits, hyphens, and underscores. Original filenames may contain other characters.

Japanese characters, accented Latin characters, and spaces in source paths are passed to ExifTool through UTF-8 input; no Windows code-page change is needed. CR, LF, and NUL control characters in paths are rejected before ExifTool runs. ExifTool documents limitations for some Windows filenames containing Unicode code points above U+FFFF, so that category is not claimed as supported. Redirected ALBUM logs use UTF-8.

ALBUM searches subfolders recursively and reads `DateTimeOriginal`, `CreateDate`, and `FileModifyDate` in that order. The date is the calendar date written in the selected metadata; sorting does not normalize timezone offsets. `FileModifyDate` is a fallback, not evidence of capture time. If none is valid, the folder name begins with `unknown_date`.

Within each date/photographer/location group, ALBUM sorts by timestamp and then filename. New files continue the existing sequence from `0001` to `9999`. It refuses to exceed `9999` or overwrite an existing destination. For example:

```text
output/
└── 20260102_yakushima/
    ├── 20260102_yoneoka0001_yakushima.jpg
    └── 20260102_yoneoka0002_yakushima.jpg
```

Recognized extensions, case-insensitively: `jpg jpeg png heic tif tiff dng cr2 cr3 nef arw raf rw2`. Hidden files and AppleDouble files are ignored. Other files are reported and retained. RAW and HEIC metadata writing depends on ExifTool's support for the particular file; the JPEG test does not validate every camera format.

Every new copy is SHA-256 verified. Exact duplicates anywhere in `output` and within the current input batch are skipped. Perceptually similar or resized photographs are not considered duplicates. Hidden `.filename.album.json` records link original hashes to ALBUM's GPS-edited copies. Keep these records with the output library to preserve duplicate detection after geotagging. External edits invalidate the link until that file is imported again; ALBUM does not trust a record whose output hash no longer matches.

To delete successfully copied inputs, add `--remove-input`. ALBUM verifies the output and rechecks the source hash before deletion. Duplicates, unsupported files, and failed copies remain in the input folder. A backup remains your responsibility. Do not edit these files or run multiple ALBUM processes against one project at the same time.

## 3. Add location metadata

Copy timed GPS logs to `input_gps` and run:

```bash
./album --photographer yoneoka --location yakushima --geotag --gps-timezone +09:00
```

To geotag an existing output library without copying:

```bash
./album --geotag-only --gps-timezone +09:00
```

Version 0.3.0 processes only `output` by default, including previously organized photos there. Add `--geotag-input` only when you also want to modify original files in `input_image`. ALBUM first makes a verified sibling backup named, for example, `sample.jpg.album-original`. It never overwrites an existing backup. A pre-existing backup causes that input's write to fail; inspect it before deciding what to do.

Only photographs without a valid latitude/longitude pair are updated. Existing GPS is retained. ALBUM edits a temporary copy, reads its GPS values back, then replaces the target. A failed write or read-back leaves the target in place. Unsupported formats fail individually and are counted as errors.

### Clock and matching rules

- GPS matching uses `DateTimeOriginal` or `CreateDate`; it never substitutes file modification time.
- EXIF `OffsetTimeOriginal`, `OffsetTimeDigitized`, or an embedded offset is respected when present. Otherwise the camera timestamp is interpreted in `--gps-timezone`.
- Use an explicit fixed UTC offset such as `+09:00` or `--gps-timezone=-05:00`. Without it, ALBUM uses the computer's **current** offset. It does not infer historical daylight-saving offsets or IANA zones. Split a dataset if the camera's timezone changed.
- NMEA RMC timestamps are UTC. GPX/KML/GeoJSON timestamps with offsets are converted into the selected camera timezone. Zone-free timestamps are treated as already local.
- The default maximum distance in time is 300 seconds. Set `--gps-max-gap-seconds 120` to change it. Zero requires an exact match.
- If both surrounding points belong to the same log and each is within the limit, ALBUM interpolates latitude and the shortest longitude displacement, including the date line. Otherwise it uses the nearest eligible point; an equal-distance tie chooses the earlier point.
- This is linear interpolation in geographic coordinates, not terrain-aware or geodesic reconstruction. It can cross gaps within one log. Avoid mixed tracks from different devices, overlapping trips, and long gaps. No clock-drift, movement-speed, or GPS-accuracy model is applied.

### GPS formats

| Format | Required content |
| --- | --- |
| `.log` | Active `$GPRMC` or `$GNRMC` records. Present checksums are validated. Records without a checksum remain accepted. |
| `.gpx` | `trkpt`, `rtept`, or `wpt` with coordinates and `time`. |
| `.kml` | Timed `gx:Track` coordinates or timestamped Point placemarks. A visible route without per-point times is insufficient. |
| `.geojson`, `.json` | Feature or FeatureCollection. Timestamp properties: `time`, `time_created`, `timestamp`, `coordTime`, `updated_date`; numeric timestamps are Unix seconds. A fourth coordinate value is interpreted as Unix seconds, a supported extension rather than standard GeoJSON semantics. |

Coordinates use latitude/longitude in degrees; ALBUM assumes WGS84-compatible inputs. It does not reproject another coordinate system. Missing or unusable points are omitted; an unreadable file produces an error. A file with no usable timestamps is reported as `GPS_NO_TIMED_POINTS`.

## 4. Read CSV reports and messages

Each output folder receives `album_gps.csv`. If `--geotag-input` is used, input results are in `output/input_image_gps.csv`. CSV fields are:

| Field | Meaning |
| --- | --- |
| `photo_name` | Project-relative path, including subfolders, to distinguish repeated input names. This differs from 0.2.1's basename-only field. |
| `shot_date` | Capture timestamp converted to the selected camera timezone when an explicit metadata offset exists; no UTC suffix. |
| `latitude`, `longitude` | Decimal degrees, eight decimal places; blank when unavailable. |

Decimal precision does not imply positioning accuracy. The CSV is replaced on each geotag run and reflects that run's processed files. It is a convenience report, not a complete historical audit. Keep run logs and original GPS logs when provenance matters. Coordinates can reveal sensitive collection sites; review reports before sharing them.

`COPIED`, `SKIPPED_DUPLICATE`, and `GEOTAGGED` identify completed actions. `GPS_NO_DATETIME` means no usable capture time; `GPS_NO_MATCH` means no point passed the time limit. `Errors: 0` means no reported processing failure, not that inferred positions were independently validated. Exit code is 0 for completion, 1 for processing/I/O errors, and 2 for invalid arguments. Ctrl+C interrupts the run; review the output before resuming.

## 5. Options and recovery

| Option | Purpose |
| --- | --- |
| `--project-dir PATH` | Select the folder containing the three data folders. |
| `--photographer NAME` | Name in copied filenames; required unless geotag-only. |
| `--location NAME` | Location label; default `unannotated`. |
| `--remove-input` | Delete successfully verified, unchanged copied sources. |
| `--geotag` | Geotag outputs after copying. |
| `--geotag-only` | Geotag the output library without copying; cannot combine with `--remove-input`. |
| `--geotag-input` | Also update inputs and retain `.album-original` backups. |
| `--gps-timezone OFFSET` | Camera's fixed UTC offset. |
| `--gps-max-gap-seconds N` | Maximum allowed time difference; default 300. |
| `--version`, `--help` | Print version or argument help; neither needs ExifTool. |

If ExifTool is missing, restore the complete release folder or install it for source use. If permission is denied, choose a writable project folder. If a GPS write fails, the original target is retained and the summary reports an error. To undo an input GPS edit, stop ALBUM, retain the edited file separately, and restore the `.album-original` backup under its original filename. Default output-only edits can be undone by retaining the old library separately and rebuilding from original inputs.

For a bug report, include OS, ALBUM version, command, expected result, actual result, and a small nonconfidential reproduction. Do not attach private photographs or sensitive GPS locations without intending to publish them.
