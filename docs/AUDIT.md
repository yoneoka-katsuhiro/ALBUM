# ALBUM 0.3.0 audit / 総点検記録

Audit dates: 4–5 November 2026. Baseline: `6d24a82` (v0.2.1). Scope: the full `album.py`, shell launcher, file/GPS workflow, documentation, and desktop distribution. No AGENTS.md was present in this repository.

The work applies [ai-biocode-kata](https://github.com/dritoshi/ai-biocode-kata/tree/main/chapters), specifically chapters 01 (simple contracts and separation of concerns), 08 (regressions and CI), 09 (small reproductions), 10 (deliverables), 18 (documentation), and appendix C. The existing CLI was retained; the audit did not replace it with an untested new interface.

## Findings and corrections

| Finding in 0.2.1 | Correction in 0.3.0 | Evidence |
| --- | --- | --- |
| Copying could overwrite a destination created after filename selection. | Exclusive file creation; only a newly created failed copy is removed. | Existing-content and failed-hash regressions. |
| GPS processing modified inputs as well as outputs, contrary to the expectation of retaining originals. | Output-only default; explicit `--geotag-input` retains verified backups. | Default target regression and real CLI input-hash check. |
| GPS writes operated directly on targets. | Temporary copy, ExifTool write, coordinate read-back, then replace. | Write failure and read-back mismatch preserve target bytes. |
| Changing an input between copy and deletion could lose new content. | Rehash immediately before requested deletion. | Mutation-during-copy regression. Concurrent writers remain unsupported. |
| File modification time could be mistaken for capture time during GPS matching. | Capture tags only for GPS; sorting fallback explicitly documented. | Missing capture-time regression. |
| EXIF timezone offsets were discarded. | Honor embedded offsets and EXIF offset tags. | UTC conversion regression and actual JPEG with `+09:00`. |
| Longitude interpolation crossed the globe at the date line. | Interpolate the shortest longitude displacement. | 179° to −179° midpoint test. |
| Points from unrelated logs could be interpolated together. | Require matching source log identity for interpolation. | Two-log regression. Same-log segment gaps remain a limitation. |
| NMEA checksums and invalid coordinate minutes were ignored; fractions were truncated. | Validate present checksums and minute range; retain subsecond precision. | Valid/bad checksum, 60+ minute, fraction regressions. |
| An Olympus logger header could override an explicitly selected timezone. | Keep RMC UTC interpretation and the selected camera timezone. | Header-offset regression. |
| Geotagged output hashes no longer matched retained originals on a second run. | Hash-verified provenance records link original and current output. External edits invalidate the link. | Reimport regression, external-edit regression, real CLI second-run check. |
| Symbolic links could target data outside a project; frozen paths would resolve into runtime files. | Exclude links, reject linked data folders, use executable location and `--project-dir`. | Discovery regression and frozen smoke with a separate project directory. |
| CSV basenames were ambiguous for repeated names in subfolders. | Write project-relative paths. | Real integration CSV assertion. |
| No automated tests or native build configuration. | Regression tests, lint/format settings, macOS/Windows CI, bundled-runtime packages and checksums. | See commands below and Actions results. |
| Windows CI exposed code-page loss in Japanese filenames passed to ExifTool. | Send UTF-8 arguments through stdin with `filename=UTF8` before `-@`; preserve UTF-8 redirected logs. | Unicode transport regression, control-character rejection, and native JPEG/GPX smoke retaining Japanese paths and adding Japanese/accented filenames. |

## Validation

The first targeted suite had 12 tests: 11 failed against the baseline and one passed. After fixes, additional safety cases, and four regressions for the Windows Unicode transport, **27 tests pass** locally. The Unicode transport regression failed before the fix. This records a demonstrated improvement rather than a claim that all possible bugs are excluded.

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python scripts/smoke_test.py
python scripts/build_release.py
python scripts/smoke_test.py --executable dist/album/album --exiftool dist/album/exiftool/exiftool
```

The integration test uses a generated JPEG and two timed GPX points. It verifies the expected 35.001° / 139.001° coordinate, unchanged original SHA-256, identical decoded image pixels, a complete relative path in the CSV, and zero new copies on the second run. This is a local synthetic test, not a benchmark on field photographs. The display in the README is rendered from this actual result; it is not an application GUI screenshot.

Local frozen verification completed on macOS 15.7.9 ARM64 using Python 3.13.9, PyInstaller 6.20.0, and bundled ExifTool 13.55. Both source and standalone executable passed the JPEG/GPX round trip. The package's build metadata records the full environment; the CI environment uses Python 3.12 and is checked separately.

Native tests must pass on the target operating system before its archive is released; CI is preferred. If macOS CI is queued, a locally built archive may be released after the same native tests pass. Release notes must identify the build environment and distinguish local macOS verification from Windows CI verification. Windows CI validates automated execution on Windows Server 2022; hands-on Windows 10/11 acceptance remains separate. See the release notes and [Actions](https://github.com/yoneoka-katsuhiro/ALBUM/actions) for the outcome of the specific published build.

## Remaining limits / 残る制約

- GPS is an estimate based on synchronized clocks and compatible geographic coordinates. It is not a survey instrument. No clock drift, speed, accuracy, historical DST, reprojection, or segment-gap model is provided.
- The JPEG round trip does not validate every RAW or HEIC variant. Keep originals and review camera-specific results.
- Duplicate detection is byte-based plus ALBUM's verified provenance. There is no perceptual matching or full import journal. Legacy 0.2.1 geotagged outputs have no provenance and may be imported again.
- One process per project is supported. Exclusive destination creation protects names, but this is not a transactional database or a guarantee against simultaneous external editing, hardware failure, or filesystem corruption.
- CSV reports are overwritten and are not a historical audit. An interrupted run may leave an incomplete new copy or temporary file; review before resuming.
- Standard-library runtime code has no third-party Python dependencies. ExifTool and frozen-runtime components still need updates and platform testing. No signed installer, notarization, Intel Mac build, or graphical interface is claimed.

日本語要約: 原本保護、時差・GPS補間、重複除外、コピー競合を優先して修正しました。修正前に失敗する回帰例を作り、実際のExifToolによるJPEG処理も確認しています。全RAW形式、過去の夏時間、同時実行、位置精度まで保証するものではありません。追加案は[ROADMAP](ROADMAP.md)に分けて記載しています。
