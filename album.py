#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


VERSION = "0.3.0"
INPUT_IMAGE_DIRNAME = "input_image"
INPUT_GPS_DIRNAME = "input_gps"
OUTPUT_DIRNAME = "output"
SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".tif",
    ".tiff",
    ".dng",
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".raf",
    ".rw2",
}
GPS_LOG_EXTENSIONS = {".log", ".gpx", ".kml", ".geojson", ".json"}
DATE_TAGS = ("DateTimeOriginal", "CreateDate", "FileModifyDate")
SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
UTC_OFFSET_PATTERN = re.compile(r"^(?P<sign>[+-])(?P<hour>\d{2}):?(?P<minute>\d{2})$")
EXIF_DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})[:/-](?P<month>\d{2})[:/-](?P<day>\d{2})"
    r"[ T]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)
TEXT_DATETIME_PATTERN = re.compile(
    r"(?P<year>\d{4})[/-](?P<month>\d{2})[/-](?P<day>\d{2})"
    r"[ T]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
)


@dataclass(frozen=True)
class PhotoDate:
    date_token: str
    sort_value: Optional[datetime]


@dataclass(frozen=True)
class PhotoCandidate:
    path: Path
    sha256: str
    photo_date: PhotoDate


@dataclass(frozen=True)
class GPSPoint:
    timestamp: datetime
    latitude: float
    longitude: float
    source: str


@dataclass(frozen=True)
class GeotagPhotoInfo:
    path: Path
    shot_datetime: Optional[datetime]
    latitude: Optional[float]
    longitude: Optional[float]


@dataclass(frozen=True)
class GeotagRecord:
    path: Path
    shot_datetime: Optional[datetime]
    latitude: Optional[float]
    longitude: Optional[float]


@dataclass
class Summary:
    copied: int = 0
    input_deleted: int = 0
    duplicates_skipped: int = 0
    unknown_date: int = 0
    unsupported_skipped: int = 0
    geotagged: int = 0
    gps_already_present: int = 0
    gps_no_datetime: int = 0
    gps_no_match: int = 0
    gps_csv_files: int = 0
    errors: int = 0


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ALBUM: sort and rename photos by shooting date.")
    parser.add_argument("--version", action="version", version=f"ALBUM {VERSION}")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=default_project_dir(),
        help="Folder containing input_image/, input_gps/, and output/.",
    )
    parser.add_argument("--photographer", help="Photographer name.")
    parser.add_argument(
        "--location",
        default="unannotated",
        help="Optional shooting location. Default: unannotated.",
    )
    parser.add_argument(
        "--remove-input",
        dest="remove_input",
        action="store_true",
        help=(
            "Delete each supported input file only after its output copy "
            "passes SHA-256 verification."
        ),
    )
    parser.add_argument(
        "--delete-input-after-copy",
        dest="remove_input",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--geotag",
        action="store_true",
        help="Add missing GPS coordinates from files in input_gps/ after copying.",
    )
    parser.add_argument(
        "--geotag-only",
        action="store_true",
        help="Only add missing GPS coordinates and write CSV reports.",
    )
    parser.add_argument(
        "--geotag-input",
        action="store_true",
        help="Also geotag input originals; preserve .album-original backups.",
    )
    parser.add_argument(
        "--gps-max-gap-seconds",
        type=int,
        default=300,
        help="Maximum allowed time gap between a photo and GPS points. Default: 300.",
    )
    parser.add_argument(
        "--gps-timezone",
        help=(
            "Local timezone used to compare camera timestamps with GPS logs, "
            "for example +09:00. Default: system local timezone."
        ),
    )
    args = parser.parse_args(argv)
    if args.geotag_input and not (args.geotag or args.geotag_only):
        parser.error("--geotag-input requires --geotag or --geotag-only.")
    if args.geotag_only:
        args.geotag = True
        if args.remove_input:
            parser.error("--remove-input cannot be used with --geotag-only.")
    elif not args.photographer:
        parser.error("--photographer is required unless --geotag-only is used.")
    if args.photographer:
        validate_safe_token(parser, "--photographer", args.photographer)
    validate_safe_token(parser, "--location", args.location)
    if args.gps_max_gap_seconds < 0:
        parser.error("--gps-max-gap-seconds must be 0 or greater.")
    try:
        args.gps_timezone_info = (
            parse_utc_offset(args.gps_timezone) if args.gps_timezone else local_timezone()
        )
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    return args


def default_project_dir() -> Path:
    """Keep user data beside the executable, never inside PyInstaller's runtime."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def validate_safe_token(parser: argparse.ArgumentParser, argument_name: str, value: str) -> None:
    if SAFE_TOKEN_PATTERN.fullmatch(value):
        return
    parser.error(f"Invalid {argument_name}: {value!r}. Use only these characters: A-Z a-z 0-9 - _")


def parse_utc_offset(value: str) -> timezone:
    match = UTC_OFFSET_PATTERN.fullmatch(value.strip())
    if not match:
        raise argparse.ArgumentTypeError("Use a UTC offset such as +09:00, +0900, or -05:00.")
    hours = int(match.group("hour"))
    minutes = int(match.group("minute"))
    if hours > 23 or minutes > 59:
        raise argparse.ArgumentTypeError("UTC offset is out of range.")
    delta = timedelta(hours=hours, minutes=minutes)
    if match.group("sign") == "-":
        delta = -delta
    return timezone(delta)


def local_timezone() -> timezone:
    tzinfo = datetime.now().astimezone().tzinfo
    return tzinfo if isinstance(tzinfo, timezone) else timezone.utc


def enable_line_buffering() -> None:
    # Redirected Windows streams may otherwise use a code page that cannot
    # represent filenames. Keep CLI logs portable without changing OS settings.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace", line_buffering=True)


def emit(message: str) -> None:
    print(message, flush=True)


def emit_progress(label: str, current: int, total: int, every: int = 100) -> None:
    if total == 0:
        return
    if current == 1 or current == total or current % every == 0:
        emit(f"{label}: {current}/{total}")


def ensure_exiftool() -> str:
    bundled = (
        default_project_dir()
        / "exiftool"
        / ("exiftool.exe" if sys.platform == "win32" else "exiftool")
    )
    if bundled.is_file():
        return str(bundled)
    exiftool = shutil.which("exiftool")
    if exiftool:
        return exiftool
    print("Error: ExifTool is not installed.", file=sys.stderr)
    print(
        "Install ExifTool from https://exiftool.org/ (macOS: brew install exiftool).",
        file=sys.stderr,
    )
    raise SystemExit(1)


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_ignored_path(path: Path, base_dir: Path) -> bool:
    if path.is_symlink() or any(
        parent.is_symlink() for parent in path.parents if is_relative_to(parent, base_dir)
    ):
        return True
    try:
        parts = path.relative_to(base_dir).parts
    except ValueError:
        parts = path.parts
    return any(part.startswith(".") for part in parts) or path.name.startswith("._")


def discover_input_files(input_dir: Path) -> tuple[list[Path], list[Path]]:
    supported: list[Path] = []
    unsupported: list[Path] = []
    for path in sorted(input_dir.rglob("*"), key=lambda item: str(item)):
        if not path.is_file() or is_ignored_path(path, input_dir):
            continue
        if is_supported_image(path):
            supported.append(path)
        else:
            unsupported.append(path)
    return supported, unsupported


def discover_output_images(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    return [
        path
        for path in sorted(output_dir.rglob("*"), key=lambda item: str(item))
        if path.is_file() and not is_ignored_path(path, output_dir) and is_supported_image(path)
    ]


def discover_images(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    return [
        path
        for path in sorted(base_dir.rglob("*"), key=lambda item: str(item))
        if path.is_file() and not is_ignored_path(path, base_dir) and is_supported_image(path)
    ]


def discover_gps_files(input_gps_dir: Path) -> tuple[list[Path], list[Path]]:
    supported: list[Path] = []
    unsupported: list[Path] = []
    if not input_gps_dir.exists():
        return supported, unsupported
    for path in sorted(input_gps_dir.rglob("*"), key=lambda item: str(item)):
        if not path.is_file() or is_ignored_path(path, input_gps_dir):
            continue
        if path.suffix.lower() in GPS_LOG_EXTENSIONS:
            supported.append(path)
        else:
            unsupported.append(path)
    return supported, unsupported


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def existing_output_hashes(output_dir: Path, summary: Summary) -> set[str]:
    hashes: set[str] = set()
    output_images = discover_output_images(output_dir)
    emit(f"SCAN_OUTPUT: supported={len(output_images)}")
    for index, path in enumerate(output_images, start=1):
        emit_progress("PROGRESS_HASH_OUTPUT", index, len(output_images))
        try:
            current_hash = sha256_file(path)
            hashes.add(current_hash)
            record = read_copy_provenance(path)
            if record.get("output_sha256") == current_hash:
                source_hash = record.get("source_sha256")
                if isinstance(source_hash, str):
                    hashes.add(source_hash)
        except OSError as exc:
            emit(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
    return hashes


def provenance_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.album.json")


def read_copy_provenance(path: Path) -> dict:
    try:
        record = json.loads(provenance_path(path).read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        return {}


def record_copy_provenance(path: Path, source_hash: str) -> None:
    """Link the input hash to a verified output hash, including later GPS edits."""
    record = {
        "album_version": VERSION,
        "source_sha256": source_hash,
        "output_sha256": sha256_file(path),
    }
    target = provenance_path(path)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=target.parent, delete=False, encoding="utf-8"
    ) as file:
        temporary = Path(file.name)
        json.dump(record, file, indent=2)
        file.write("\n")
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def refresh_copy_provenance(path: Path, previous_hash: str) -> None:
    record = read_copy_provenance(path)
    if record.get("output_sha256") == previous_hash and isinstance(
        record.get("source_sha256"), str
    ):
        record_copy_provenance(path, record["source_sha256"])


def run_exiftool(command: list[str]) -> subprocess.CompletedProcess:
    """Pass UTF-8 arguments through stdin, avoiding Windows argv recoding.

    ExifTool requires filename=UTF8 before -@ to enable wide-character file I/O.
    Each argument occupies one unquoted line; paths containing line breaks are
    rejected so a filename can never introduce another ExifTool option.
    """
    arguments = command[1:]
    if any(any(character in argument for character in "\r\n\0") for argument in arguments):
        raise RuntimeError("ExifTool arguments cannot contain CR, LF, or NUL control characters")
    try:
        result = subprocess.run(
            [command[0], "-charset", "filename=UTF8", "-@", "-"],
            input="\n".join(arguments) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Cannot run ExifTool: {exc}") from exc
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "ExifTool failed.")
    return result


def read_photo_date(exiftool: str, path: Path) -> PhotoDate:
    command = [
        exiftool,
        "-json",
        "-DateTimeOriginal",
        "-CreateDate",
        "-FileModifyDate",
        str(path),
    ]
    result = run_exiftool(command)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "ExifTool failed.")

    try:
        values = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ExifTool returned invalid JSON: {exc}") from exc

    metadata = values[0] if values else {}
    for tag in DATE_TAGS:
        value = metadata.get(tag)
        if not isinstance(value, str) or not value.strip():
            continue
        parsed = parse_exif_datetime(value)
        if parsed:
            return PhotoDate(date_token=parsed.strftime("%Y%m%d"), sort_value=parsed)
    return PhotoDate(date_token="unknown_date", sort_value=None)


def read_geotag_photo_info(
    exiftool: str, path: Path, local_tz: timezone = timezone.utc
) -> GeotagPhotoInfo:
    command = [
        exiftool,
        "-json",
        "-n",
        "-DateTimeOriginal",
        "-CreateDate",
        "-OffsetTimeOriginal",
        "-OffsetTimeDigitized",
        "-GPSLatitude",
        "-GPSLongitude",
        str(path),
    ]
    result = run_exiftool(command)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "ExifTool failed.")

    try:
        values = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ExifTool returned invalid JSON: {exc}") from exc

    metadata = values[0] if values else {}
    shot_datetime = metadata_datetime(metadata, local_tz)
    latitude = metadata_float(metadata.get("GPSLatitude"))
    longitude = metadata_float(metadata.get("GPSLongitude"))
    if not valid_coordinate(latitude, longitude):
        latitude = None
        longitude = None
    return GeotagPhotoInfo(
        path=path,
        shot_datetime=shot_datetime,
        latitude=latitude,
        longitude=longitude,
    )


def metadata_datetime(
    metadata: dict[str, object], local_tz: timezone = timezone.utc
) -> Optional[datetime]:
    """Use capture timestamps only; filesystem modification is not capture time."""
    for tag, offset_tag in (
        ("DateTimeOriginal", "OffsetTimeOriginal"),
        ("CreateDate", "OffsetTimeDigitized"),
    ):
        value = metadata.get(tag)
        if not isinstance(value, str) or not value.strip():
            continue
        parsed = parse_exif_datetime(value)
        if parsed:
            offset = metadata.get(offset_tag)
            embedded = re.search(r"([+-]\d{2}:?\d{2}|Z)$", value.strip())
            if embedded:
                offset = "+00:00" if embedded[1] == "Z" else embedded[1]
            if isinstance(offset, str) and offset.strip():
                try:
                    parsed = parsed.replace(tzinfo=parse_utc_offset(offset))
                except argparse.ArgumentTypeError:
                    return None
                return parsed.astimezone(local_tz).replace(tzinfo=None)
            return parsed
    return None


def metadata_float(value: object) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def valid_coordinate(latitude: Optional[float], longitude: Optional[float]) -> bool:
    if latitude is None or longitude is None:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def parse_exif_datetime(value: str) -> Optional[datetime]:
    match = EXIF_DATE_PATTERN.search(value.strip())
    if not match:
        return None
    try:
        return datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
        )
    except ValueError:
        return None


def parse_text_datetime(value: str) -> Optional[datetime]:
    match = TEXT_DATETIME_PATTERN.search(value.strip())
    if not match:
        return None
    try:
        return datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second")),
        )
    except ValueError:
        return None


def parse_iso_datetime_to_local(value: str, local_tz: timezone) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        local = parse_text_datetime(value)
        return local
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(local_tz).replace(tzinfo=None)


def parse_epoch_to_local(value: object, local_tz: timezone) -> Optional[datetime]:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    try:
        return (
            datetime.fromtimestamp(seconds, tz=timezone.utc)
            .astimezone(local_tz)
            .replace(tzinfo=None)
        )
    except (OSError, OverflowError, ValueError):
        return None


def parse_gps_points(input_gps_dir: Path, local_tz: timezone, summary: Summary) -> list[GPSPoint]:
    gps_files, unsupported = discover_gps_files(input_gps_dir)
    for path in unsupported:
        emit(f"GPS_SKIPPED_UNSUPPORTED: {display_path(path)}")
    emit(f"SCAN_GPS: files={len(gps_files)}")

    points: list[GPSPoint] = []
    for path in gps_files:
        try:
            parsed = parse_gps_file(path, local_tz)
        except Exception as exc:
            emit(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
            continue
        if not parsed:
            emit(f"GPS_NO_TIMED_POINTS: {display_path(path)}")
        else:
            emit(f"GPS_POINTS: {display_path(path)} points={len(parsed)}")
            points.extend(parsed)
    points.sort(key=lambda point: point.timestamp)
    emit(f"GPS_POINTS_TOTAL: {len(points)}")
    return points


def parse_gps_file(path: Path, local_tz: timezone) -> list[GPSPoint]:
    extension = path.suffix.lower()
    if extension == ".log":
        return parse_nmea_log(path, local_tz)
    if extension == ".gpx":
        return parse_gpx(path, local_tz)
    if extension == ".kml":
        return parse_kml(path, local_tz)
    if extension in {".geojson", ".json"}:
        return parse_geojson(path, local_tz)
    return []


def parse_nmea_log(path: Path, fallback_tz: timezone) -> list[GPSPoint]:
    points: list[GPSPoint] = []
    local_tz = fallback_tz
    with path.open("r", encoding="utf-8", errors="replace", newline=None) as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            if text.startswith("@"):
                # NMEA RMC timestamps are UTC; a logger header must not override
                # the explicitly selected camera timezone.
                continue
            if not text.startswith(("$GPRMC", "$GNRMC")):
                continue
            point = parse_rmc_sentence(text, local_tz, str(path))
            if point:
                points.append(point)
    return points


def parse_rmc_sentence(sentence: str, local_tz: timezone, source: str) -> Optional[GPSPoint]:
    body = sentence.split("*", 1)[0]
    if "*" in sentence:
        checksum = 0
        for character in body.lstrip("$"):
            checksum ^= ord(character)
        try:
            if checksum != int(sentence.split("*", 1)[1].strip(), 16):
                return None
        except ValueError:
            return None
    fields = body.split(",")
    if len(fields) < 10 or fields[2] != "A":
        return None
    timestamp = parse_nmea_datetime(fields[1], fields[9], local_tz)
    latitude = parse_nmea_coordinate(fields[3], fields[4])
    longitude = parse_nmea_coordinate(fields[5], fields[6])
    if timestamp is None or not valid_coordinate(latitude, longitude):
        return None
    return GPSPoint(timestamp=timestamp, latitude=latitude, longitude=longitude, source=source)


def parse_nmea_datetime(time_value: str, date_value: str, local_tz: timezone) -> Optional[datetime]:
    if len(time_value) < 6 or len(date_value) != 6:
        return None
    try:
        hour = int(time_value[0:2])
        minute = int(time_value[2:4])
        seconds = float(time_value[4:])
        if not math.isfinite(seconds) or not 0 <= seconds < 60:
            return None
        second = int(seconds)
        microsecond = int(round((seconds - second) * 1_000_000))
        day = int(date_value[0:2])
        month = int(date_value[2:4])
        year = int(date_value[4:6])
    except ValueError:
        return None
    year += 2000 if year < 70 else 1900
    try:
        utc_time = datetime(
            year, month, day, hour, minute, second, tzinfo=timezone.utc
        ) + timedelta(microseconds=microsecond)
    except ValueError:
        return None
    return utc_time.astimezone(local_tz).replace(tzinfo=None)


def parse_nmea_coordinate(value: str, hemisphere: str) -> Optional[float]:
    if not value or hemisphere not in {"N", "S", "E", "W"}:
        return None
    degree_digits = 2 if hemisphere in {"N", "S"} else 3
    if len(value) <= degree_digits:
        return None
    try:
        degrees = int(value[:degree_digits])
        minutes = float(value[degree_digits:])
    except ValueError:
        return None
    if degrees < 0 or not 0 <= minutes < 60:
        return None
    coordinate = degrees + minutes / 60.0
    if hemisphere in {"S", "W"}:
        coordinate = -coordinate
    return coordinate


def parse_gpx(path: Path, local_tz: timezone) -> list[GPSPoint]:
    root = ET.parse(path).getroot()
    points: list[GPSPoint] = []
    for element in root.iter():
        if element_name(element) not in {"trkpt", "rtept", "wpt"}:
            continue
        latitude = metadata_float(element.attrib.get("lat"))
        longitude = metadata_float(element.attrib.get("lon"))
        time_text = child_text(element, "time")
        timestamp = parse_iso_datetime_to_local(time_text, local_tz) if time_text else None
        if timestamp and valid_coordinate(latitude, longitude):
            points.append(
                GPSPoint(
                    timestamp=timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    source=str(path),
                )
            )
    return points


def parse_kml(path: Path, local_tz: timezone) -> list[GPSPoint]:
    root = ET.parse(path).getroot()
    points: list[GPSPoint] = []
    for track in root.iter():
        if element_name(track) != "Track":
            continue
        whens = [item.text or "" for item in track.iter() if element_name(item) == "when"]
        coords = [item.text or "" for item in track.iter() if element_name(item) == "coord"]
        for when_text, coord_text in zip(whens, coords):
            timestamp = parse_iso_datetime_to_local(when_text, local_tz)
            coordinate = parse_kml_coordinate(coord_text)
            if timestamp and coordinate:
                latitude, longitude = coordinate
                points.append(
                    GPSPoint(
                        timestamp=timestamp,
                        latitude=latitude,
                        longitude=longitude,
                        source=str(path),
                    )
                )

    for placemark in root.iter():
        if element_name(placemark) != "Placemark":
            continue
        timestamp = placemark_timestamp(placemark, local_tz)
        if not timestamp:
            continue
        coordinate = placemark_point_coordinate(placemark)
        if coordinate:
            latitude, longitude = coordinate
            points.append(
                GPSPoint(
                    timestamp=timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    source=str(path),
                )
            )
    return points


def parse_geojson(path: Path, local_tz: timezone) -> list[GPSPoint]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    points: list[GPSPoint] = []
    for feature in geojson_features(data):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates")
        for coordinate in iter_geojson_coordinates(coordinates):
            if len(coordinate) >= 4:
                timestamp = parse_epoch_to_local(coordinate[3], local_tz)
            else:
                timestamp = property_timestamp(properties, local_tz)
            longitude = metadata_float(coordinate[0]) if len(coordinate) > 0 else None
            latitude = metadata_float(coordinate[1]) if len(coordinate) > 1 else None
            if timestamp and valid_coordinate(latitude, longitude):
                points.append(
                    GPSPoint(
                        timestamp=timestamp,
                        latitude=latitude,
                        longitude=longitude,
                        source=str(path),
                    )
                )
    return points


def geojson_features(data: object) -> list[dict[str, object]]:
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        features = data.get("features")
        if isinstance(features, list):
            return [item for item in features if isinstance(item, dict)]
        return []
    if isinstance(data, dict) and data.get("type") == "Feature":
        return [data]
    return []


def iter_geojson_coordinates(value: object) -> list[list[object]]:
    if not isinstance(value, list):
        return []
    if value and all(isinstance(item, (int, float, str)) for item in value):
        return [value]
    coordinates: list[list[object]] = []
    for item in value:
        coordinates.extend(iter_geojson_coordinates(item))
    return coordinates


def property_timestamp(properties: object, local_tz: timezone) -> Optional[datetime]:
    if not isinstance(properties, dict):
        return None
    for key in ("time", "time_created", "timestamp", "coordTime", "updated_date"):
        value = properties.get(key)
        if isinstance(value, str):
            parsed = parse_iso_datetime_to_local(value, local_tz)
            if parsed:
                return parsed
        elif value is not None:
            parsed = parse_epoch_to_local(value, local_tz)
            if parsed:
                return parsed
    return None


def element_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, name: str) -> Optional[str]:
    for child in element:
        if element_name(child) == name:
            return child.text
    return None


def placemark_timestamp(placemark: ET.Element, local_tz: timezone) -> Optional[datetime]:
    for element in placemark.iter():
        if element_name(element) == "when" and element.text:
            parsed = parse_iso_datetime_to_local(element.text, local_tz)
            if parsed:
                return parsed
    texts = [element.text or "" for element in placemark.iter() if element.text]
    for text in texts:
        parsed = parse_text_datetime(text)
        if parsed:
            return parsed
    return None


def placemark_point_coordinate(placemark: ET.Element) -> Optional[tuple[float, float]]:
    in_point = False
    for element in placemark.iter():
        name = element_name(element)
        if name == "Point":
            in_point = True
            continue
        if in_point and name == "coordinates" and element.text:
            return parse_kml_coordinate(element.text)
    return None


def parse_kml_coordinate(value: str) -> Optional[tuple[float, float]]:
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) < 2:
        return None
    longitude = metadata_float(parts[0])
    latitude = metadata_float(parts[1])
    if not valid_coordinate(latitude, longitude):
        return None
    return latitude, longitude


def collect_candidates(
    input_images: list[Path],
    output_hashes: set[str],
    exiftool: str,
    summary: Summary,
) -> list[PhotoCandidate]:
    candidates: list[PhotoCandidate] = []
    seen_new_hashes: set[str] = set()
    for index, path in enumerate(input_images, start=1):
        emit_progress("PROGRESS_READ_INPUT", index, len(input_images))
        try:
            file_hash = sha256_file(path)
        except OSError as exc:
            emit(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
            continue

        if file_hash in output_hashes or file_hash in seen_new_hashes:
            emit(f"SKIPPED_DUPLICATE: {display_path(path)}")
            summary.duplicates_skipped += 1
            continue

        try:
            photo_date = read_photo_date(exiftool, path)
        except RuntimeError as exc:
            emit(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
            continue
        seen_new_hashes.add(file_hash)
        candidates.append(PhotoCandidate(path=path, sha256=file_hash, photo_date=photo_date))
    return candidates


def group_candidates(
    candidates: list[PhotoCandidate], photographer: str, location: str
) -> dict[tuple[str, str, str], list[PhotoCandidate]]:
    groups: dict[tuple[str, str, str], list[PhotoCandidate]] = {}
    for candidate in candidates:
        key = (candidate.photo_date.date_token, photographer, location)
        groups.setdefault(key, []).append(candidate)
    for grouped in groups.values():
        grouped.sort(
            key=lambda item: (
                item.photo_date.sort_value is None,
                item.photo_date.sort_value or datetime.min,
                item.path.name,
            )
        )
    return groups


def existing_max_number(folder: Path, date_token: str, photographer: str, location: str) -> int:
    if not folder.exists():
        return 0
    pattern = re.compile(
        rf"^{re.escape(date_token)}_"
        rf"{re.escape(photographer)}(?P<number>\d{{4}})_"
        rf"{re.escape(location)}\.[^.]+$"
    )
    maximum = 0
    for path in folder.iterdir():
        if not path.is_file() or not is_supported_image(path):
            continue
        match = pattern.fullmatch(path.name)
        if match:
            maximum = max(maximum, int(match.group("number")))
    return maximum


def destination_for(
    output_dir: Path,
    candidate: PhotoCandidate,
    photographer: str,
    location: str,
    number: int,
) -> Path:
    date_token = candidate.photo_date.date_token
    folder = output_dir / f"{date_token}_{location}"
    filename = f"{date_token}_{photographer}{number:04d}_{location}{candidate.path.suffix}"
    return folder / filename


def copy_and_verify(
    source: Path,
    destination: Path,
    expected_hash: str,
) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        # Exclusive creation prevents overwriting files created after name selection.
        with destination.open("xb") as target:
            created = True
            with source.open("rb") as original:
                shutil.copyfileobj(original, target)
        shutil.copystat(source, destination)
        copied_hash = sha256_file(destination)
    except Exception:
        if created and destination.exists():
            destination.unlink(missing_ok=True)
        raise

    if copied_hash == expected_hash:
        return True
    if created and destination.exists():
        destination.unlink(missing_ok=True)
    return False


def copy_candidates(
    groups: dict[tuple[str, str, str], list[PhotoCandidate]],
    output_dir: Path,
    output_hashes: set[str],
    summary: Summary,
    delete_input_after_copy: bool,
) -> None:
    total_candidates = sum(len(candidates) for candidates in groups.values())
    copied_index = 0
    for (date_token, photographer, location), candidates in sorted(groups.items()):
        folder = output_dir / f"{date_token}_{location}"
        number = existing_max_number(folder, date_token, photographer, location) + 1
        for candidate in candidates:
            copied_index += 1
            emit_progress("PROGRESS_COPY", copied_index, total_candidates)
            try:
                destination = next_available_destination(
                    output_dir,
                    candidate,
                    photographer,
                    location,
                    number,
                )
            except RuntimeError as exc:
                emit(f"ERROR: {display_path(candidate.path)} ({exc})")
                summary.errors += 1
                continue
            number = extract_sequence_number(destination, photographer, location) + 1
            try:
                ok = copy_and_verify(candidate.path, destination, candidate.sha256)
            except Exception as exc:
                emit(f"ERROR: {display_path(candidate.path)} ({exc})")
                summary.errors += 1
                continue
            if not ok:
                emit(f"ERROR: {display_path(candidate.path)} (SHA-256 verification failed)")
                summary.errors += 1
                continue

            try:
                record_copy_provenance(destination, candidate.sha256)
            except OSError as exc:
                emit(f"ERROR: could not record copy provenance ({exc}); input retained")
                summary.errors += 1
                continue

            output_hashes.add(candidate.sha256)
            summary.copied += 1
            if candidate.photo_date.date_token == "unknown_date":
                summary.unknown_date += 1
                status = "UNKNOWN_DATE"
            else:
                status = "COPIED"
            emit(f"{status}: {display_path(candidate.path)} -> {display_path(destination)}")
            if delete_input_after_copy:
                try:
                    if sha256_file(candidate.path) != candidate.sha256:
                        raise OSError("input changed since copy; retained")
                    delete_input_file(candidate.path, summary)
                except OSError as exc:
                    emit(f"ERROR: {display_path(candidate.path)} ({exc})")
                    summary.errors += 1


def delete_input_file(path: Path, summary: Summary) -> None:
    try:
        path.unlink()
    except OSError as exc:
        emit(f"ERROR: {display_path(path)} (could not delete input after copy: {exc})")
        summary.errors += 1
        return
    summary.input_deleted += 1
    emit(f"DELETED_INPUT: {display_path(path)}")


def next_available_destination(
    output_dir: Path,
    candidate: PhotoCandidate,
    photographer: str,
    location: str,
    start_number: int,
) -> Path:
    number = start_number
    while number <= 9999:
        destination = destination_for(output_dir, candidate, photographer, location, number)
        if destination.parent.is_symlink():
            raise RuntimeError("refusing to write through a symbolic-link output folder")
        if not destination.exists():
            return destination
        number += 1
    raise RuntimeError("sequence number exceeded 9999")


def extract_sequence_number(path: Path, photographer: str, location: str) -> int:
    pattern = re.compile(
        rf"^.+_{re.escape(photographer)}(?P<number>\d{{4}})_"
        rf"{re.escape(location)}\.[^.]+$"
    )
    match = pattern.fullmatch(path.name)
    if not match:
        raise RuntimeError(f"could not parse sequence number from {path.name}")
    return int(match.group("number"))


def geotag_images(
    project_dir: Path,
    image_input_dir: Path,
    input_gps_dir: Path,
    output_dir: Path,
    exiftool: str,
    local_tz: timezone,
    max_gap_seconds: int,
    summary: Summary,
    include_input: bool = False,
) -> None:
    emit("GEOTAG_START: reading GPS logs")
    gps_points = parse_gps_points(input_gps_dir, local_tz, summary)
    if not gps_points:
        emit("ERROR: no timed GPS points were found in input_gps/")
        summary.errors += 1
        return

    input_images = discover_images(image_input_dir) if include_input else []
    output_images = discover_output_images(output_dir)
    targets = input_images + output_images
    emit(f"GEOTAG_TARGETS: {image_input_dir.name}={len(input_images)} output={len(output_images)}")

    records: list[GeotagRecord] = []
    timestamps = [point.timestamp for point in gps_points]
    for index, path in enumerate(targets, start=1):
        emit_progress("PROGRESS_GEOTAG", index, len(targets))
        try:
            info = read_geotag_photo_info(exiftool, path, local_tz)
        except RuntimeError as exc:
            emit(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
            continue

        if valid_coordinate(info.latitude, info.longitude):
            summary.gps_already_present += 1
            records.append(
                GeotagRecord(
                    path=path,
                    shot_datetime=info.shot_datetime,
                    latitude=info.latitude,
                    longitude=info.longitude,
                )
            )
            emit(f"GPS_ALREADY_PRESENT: {display_path(path)}")
            continue

        if info.shot_datetime is None:
            summary.gps_no_datetime += 1
            records.append(
                GeotagRecord(path=path, shot_datetime=None, latitude=None, longitude=None)
            )
            emit(f"GPS_NO_DATETIME: {display_path(path)}")
            continue

        coordinate = coordinate_for_time(
            gps_points,
            timestamps,
            info.shot_datetime,
            max_gap_seconds,
        )
        if coordinate is None:
            summary.gps_no_match += 1
            records.append(
                GeotagRecord(
                    path=path,
                    shot_datetime=info.shot_datetime,
                    latitude=None,
                    longitude=None,
                )
            )
            emit(f"GPS_NO_MATCH: {display_path(path)}")
            continue

        latitude, longitude = coordinate
        try:
            previous_hash = sha256_file(path)
            if is_relative_to(path, image_input_dir):
                backup = path.with_name(path.name + ".album-original")
                if not copy_and_verify(path, backup, sha256_file(path)):
                    raise RuntimeError("Input backup verification failed")
            write_gps_tags(exiftool, path, latitude, longitude)
            refresh_copy_provenance(path, previous_hash)
        except (RuntimeError, OSError) as exc:
            emit(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
            records.append(
                GeotagRecord(
                    path=path,
                    shot_datetime=info.shot_datetime,
                    latitude=None,
                    longitude=None,
                )
            )
            continue

        summary.geotagged += 1
        records.append(
            GeotagRecord(
                path=path,
                shot_datetime=info.shot_datetime,
                latitude=latitude,
                longitude=longitude,
            )
        )
        emit(f"GEOTAGGED: {display_path(path)} ({latitude:.7f}, {longitude:.7f})")

    write_geotag_csvs(records, project_dir, image_input_dir, output_dir, summary)


def coordinate_for_time(
    points: list[GPSPoint],
    timestamps: list[datetime],
    shot_datetime: datetime,
    max_gap_seconds: int,
) -> Optional[tuple[float, float]]:
    insertion = bisect_left(timestamps, shot_datetime)
    before = points[insertion - 1] if insertion > 0 else None
    after = points[insertion] if insertion < len(points) else None
    max_gap = timedelta(seconds=max_gap_seconds)

    if (
        before
        and after
        and before.source == after.source
        and before.timestamp <= shot_datetime <= after.timestamp
    ):
        before_gap = shot_datetime - before.timestamp
        after_gap = after.timestamp - shot_datetime
        if before_gap <= max_gap and after_gap <= max_gap:
            interval = (after.timestamp - before.timestamp).total_seconds()
            if interval <= 0:
                return before.latitude, before.longitude
            ratio = before_gap.total_seconds() / interval
            latitude = before.latitude + (after.latitude - before.latitude) * ratio
            delta = (after.longitude - before.longitude + 180) % 360 - 180
            longitude = (before.longitude + delta * ratio + 180) % 360 - 180
            return latitude, longitude

    nearest = None
    nearest_gap = None
    for candidate in (before, after):
        if candidate is None:
            continue
        gap = abs(candidate.timestamp - shot_datetime)
        if nearest_gap is None or gap < nearest_gap:
            nearest = candidate
            nearest_gap = gap
    if nearest is not None and nearest_gap is not None and nearest_gap <= max_gap:
        return nearest.latitude, nearest.longitude
    return None


def write_gps_tags(exiftool: str, path: Path, latitude: float, longitude: float) -> None:
    """Edit and validate a temporary copy before replacing the target."""
    with tempfile.NamedTemporaryFile(
        prefix=".album-gps-", suffix=path.suffix, dir=path.parent, delete=False
    ) as file:
        temporary = Path(file.name)
    try:
        shutil.copy2(path, temporary)
        _write_gps_tags(exiftool, temporary, latitude, longitude)
        check = read_geotag_photo_info(exiftool, temporary)
        if (
            check.latitude is None
            or check.longitude is None
            or abs(check.latitude - latitude) > 0.000001
            or abs(check.longitude - longitude) > 0.000001
        ):
            raise RuntimeError("GPS read-back verification failed; target retained")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_gps_tags(exiftool: str, path: Path, latitude: float, longitude: float) -> None:
    command = [
        exiftool,
        "-overwrite_original",
        "-P",
        f"-GPSLatitude={abs(latitude):.8f}",
        f"-GPSLatitudeRef={'N' if latitude >= 0 else 'S'}",
        f"-GPSLongitude={abs(longitude):.8f}",
        f"-GPSLongitudeRef={'E' if longitude >= 0 else 'W'}",
        str(path),
    ]
    result = run_exiftool(command)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "ExifTool failed while writing GPS tags.")


def write_geotag_csvs(
    records: list[GeotagRecord],
    project_dir: Path,
    image_input_dir: Path,
    output_dir: Path,
    summary: Summary,
) -> None:
    if not records:
        return

    input_records: list[GeotagRecord] = []
    output_records: dict[Path, list[GeotagRecord]] = {}
    for record in records:
        if is_relative_to(record.path, output_dir):
            output_records.setdefault(record.path.parent, []).append(record)
        elif is_relative_to(record.path, image_input_dir):
            input_records.append(record)

    if input_records:
        csv_path = output_dir / f"{INPUT_IMAGE_DIRNAME}_gps.csv"
        write_geotag_csv(csv_path, input_records, project_dir)
        summary.gps_csv_files += 1
        emit(f"CSV_WRITTEN: {display_path(csv_path)}")

    for folder, folder_records in sorted(output_records.items(), key=lambda item: str(item[0])):
        csv_path = folder / "album_gps.csv"
        write_geotag_csv(csv_path, folder_records, project_dir)
        summary.gps_csv_files += 1
        emit(f"CSV_WRITTEN: {display_path(csv_path)}")


def write_geotag_csv(csv_path: Path, records: list[GeotagRecord], project_dir: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["photo_name", "shot_date", "latitude", "longitude"])
        for record in sorted(records, key=lambda item: str(item.path)):
            writer.writerow(
                [
                    str(record.path.relative_to(project_dir)),
                    format_datetime(record.shot_datetime),
                    format_coordinate(record.latitude),
                    format_coordinate(record.longitude),
                ]
            )


def format_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def format_coordinate(value: Optional[float]) -> str:
    return f"{value:.8f}" if value is not None else ""


def is_relative_to(path: Path, base_dir: Path) -> bool:
    try:
        path.relative_to(base_dir)
    except ValueError:
        return False
    return True


def display_path(path: Path) -> str:
    project_dir = default_project_dir()
    try:
        return str(path.relative_to(project_dir))
    except ValueError:
        return str(path)


def print_unsupported(paths: list[Path], summary: Summary) -> None:
    for path in paths:
        emit(f"SKIPPED_UNSUPPORTED: {display_path(path)}")
        summary.unsupported_skipped += 1


def print_summary(summary: Summary) -> None:
    emit(f"Copied: {summary.copied}")
    emit(f"Input files deleted: {summary.input_deleted}")
    emit(f"Duplicates skipped: {summary.duplicates_skipped}")
    emit(f"Unknown date: {summary.unknown_date}")
    emit(f"Unsupported skipped: {summary.unsupported_skipped}")
    emit(f"GPS coordinates added: {summary.geotagged}")
    emit(f"GPS already present: {summary.gps_already_present}")
    emit(f"GPS no shooting date: {summary.gps_no_datetime}")
    emit(f"GPS no time match: {summary.gps_no_match}")
    emit(f"GPS CSV files written: {summary.gps_csv_files}")
    emit(f"Errors: {summary.errors}")


def _main() -> int:
    enable_line_buffering()
    args = parse_args()
    exiftool = ensure_exiftool()
    project_dir = args.project_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    input_image_dir = project_dir / INPUT_IMAGE_DIRNAME
    input_gps_dir = project_dir / INPUT_GPS_DIRNAME
    output_dir = project_dir / OUTPUT_DIRNAME
    if any(folder.is_symlink() for folder in (input_image_dir, input_gps_dir, output_dir)):
        raise OSError("Project data folders must not be symbolic links")
    input_image_dir.mkdir(exist_ok=True)
    input_gps_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    summary = Summary()
    if not args.geotag_only:
        supported, unsupported = discover_input_files(input_image_dir)
        emit(
            f"SCAN_INPUT: folder={input_image_dir.name} "
            f"supported={len(supported)} unsupported={len(unsupported)}"
        )
        print_unsupported(unsupported, summary)
        output_hashes = existing_output_hashes(output_dir, summary)
        candidates = collect_candidates(supported, output_hashes, exiftool, summary)
        groups = group_candidates(candidates, args.photographer, args.location)
        copy_candidates(
            groups,
            output_dir,
            output_hashes,
            summary,
            args.remove_input,
        )

    if args.geotag:
        geotag_images(
            project_dir,
            input_image_dir,
            input_gps_dir,
            output_dir,
            exiftool,
            args.gps_timezone_info,
            args.gps_max_gap_seconds,
            summary,
            args.geotag_input,
        )

    print_summary(summary)
    return 1 if summary.errors else 0


def main() -> int:
    try:
        return _main()
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
