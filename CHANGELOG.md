# Changelog

## 0.3.0 — 2026-11-05

### Changed

- Geotag outputs only by default. `--geotag-input` explicitly includes originals and retains verified `.album-original` backups.
- CSV `photo_name` now stores the project-relative path rather than only the basename.
- Document Python 3.11+ source support and native macOS ARM64 / Windows x64 package builds.

### Fixed

- Prevent destination overwrite during copy races and retain sources that change before requested deletion.
- Validate GPS on a temporary edited copy before replacing a target.
- Respect capture-time timezone offsets; never use file modification time for GPS matching.
- Correct date-line interpolation, avoid interpolation across distinct logs, validate NMEA checksums/minutes, and preserve fractional seconds.
- Keep duplicate detection valid after ALBUM GPS edits with hash-verified provenance; invalidate it after external edits.
- Ignore symbolic links and use stable data locations in frozen executables.
- Pass Japanese and accented filenames to ExifTool through a UTF-8 argument stream on Windows; keep redirected logs in UTF-8 and reject argument-file control characters.

### Added

- `--project-dir`, `--version`, external-tool timeouts, actionable errors, and regression tests.
- Real ExifTool JPEG/GPX integration tests for source and frozen packages.
- English/Japanese README and manuals, actual demonstration image, audit, roadmap, citation metadata, and release build guide.
- macOS/Windows test and build workflow with pinned ExifTool checksums and artifact checksums.
- Source commit and dirty-worktree state in each package's build metadata.

### Migration from 0.2.1

Existing libraries remain usable. Geotagging no longer edits inputs unless `--geotag-input` is added. Preserve the new hidden `.album.json` provenance files alongside outputs. Legacy GPS-edited outputs lack these records and may not be recognized as copies of unchanged originals. Update CSV consumers that expect basename-only `photo_name` values.

## 0.2.1

Existing public baseline: photo organization, byte-hash duplicate detection, optional source deletion, GPS log parsing, and CSV export.
