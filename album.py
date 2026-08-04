#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


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
DATE_TAGS = ("DateTimeOriginal", "CreateDate", "FileModifyDate")
SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
EXIF_DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})[:/-](?P<month>\d{2})[:/-](?P<day>\d{2})"
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


@dataclass
class Summary:
    copied: int = 0
    duplicates_skipped: int = 0
    unknown_date: int = 0
    unsupported_skipped: int = 0
    errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ALBUM: sort and rename photos by shooting date."
    )
    parser.add_argument("--photographer", required=True, help="Photographer name.")
    parser.add_argument(
        "--location",
        default="unannotated",
        help="Optional shooting location. Default: unannotated.",
    )
    args = parser.parse_args()
    validate_safe_token(parser, "--photographer", args.photographer)
    validate_safe_token(parser, "--location", args.location)
    return args


def validate_safe_token(
    parser: argparse.ArgumentParser, argument_name: str, value: str
) -> None:
    if SAFE_TOKEN_PATTERN.fullmatch(value):
        return
    parser.error(
        f"Invalid {argument_name}: {value!r}. "
        "Use only these characters: A-Z a-z 0-9 - _"
    )


def ensure_exiftool() -> str:
    exiftool = shutil.which("exiftool")
    if exiftool:
        return exiftool
    print("Error: ExifTool is not installed.", file=sys.stderr)
    print("Install it with: brew install exiftool", file=sys.stderr)
    raise SystemExit(1)


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_ignored_path(path: Path, base_dir: Path) -> bool:
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
        if path.is_file()
        and not is_ignored_path(path, output_dir)
        and is_supported_image(path)
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def existing_output_hashes(output_dir: Path, summary: Summary) -> set[str]:
    hashes: set[str] = set()
    for path in discover_output_images(output_dir):
        try:
            hashes.add(sha256_file(path))
        except OSError as exc:
            print(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
    return hashes


def read_photo_date(exiftool: str, path: Path) -> PhotoDate:
    command = [
        exiftool,
        "-json",
        "-DateTimeOriginal",
        "-CreateDate",
        "-FileModifyDate",
        str(path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
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


def collect_candidates(
    input_images: list[Path],
    output_hashes: set[str],
    exiftool: str,
    summary: Summary,
) -> list[PhotoCandidate]:
    candidates: list[PhotoCandidate] = []
    seen_new_hashes: set[str] = set()
    for path in input_images:
        try:
            file_hash = sha256_file(path)
        except OSError as exc:
            print(f"ERROR: {display_path(path)} ({exc})")
            summary.errors += 1
            continue

        if file_hash in output_hashes or file_hash in seen_new_hashes:
            print(f"SKIPPED_DUPLICATE: {display_path(path)}")
            summary.duplicates_skipped += 1
            continue

        try:
            photo_date = read_photo_date(exiftool, path)
        except RuntimeError as exc:
            print(f"ERROR: {display_path(path)} ({exc})")
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


def existing_max_number(
    folder: Path, date_token: str, photographer: str, location: str
) -> int:
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
    destination_existed = destination.exists()
    try:
        shutil.copy2(source, destination)
        copied_hash = sha256_file(destination)
    except Exception:
        if not destination_existed and destination.exists():
            destination.unlink(missing_ok=True)
        raise

    if copied_hash == expected_hash:
        return True
    if not destination_existed and destination.exists():
        destination.unlink(missing_ok=True)
    return False


def copy_candidates(
    groups: dict[tuple[str, str, str], list[PhotoCandidate]],
    output_dir: Path,
    output_hashes: set[str],
    summary: Summary,
) -> None:
    for (date_token, photographer, location), candidates in sorted(groups.items()):
        folder = output_dir / f"{date_token}_{location}"
        number = existing_max_number(folder, date_token, photographer, location) + 1
        for candidate in candidates:
            try:
                destination = next_available_destination(
                    output_dir,
                    candidate,
                    photographer,
                    location,
                    number,
                )
            except RuntimeError as exc:
                print(f"ERROR: {display_path(candidate.path)} ({exc})")
                summary.errors += 1
                continue
            number = extract_sequence_number(destination, photographer, location) + 1
            try:
                ok = copy_and_verify(candidate.path, destination, candidate.sha256)
            except Exception as exc:
                print(f"ERROR: {display_path(candidate.path)} ({exc})")
                summary.errors += 1
                continue
            if not ok:
                print(f"ERROR: {display_path(candidate.path)} (SHA-256 verification failed)")
                summary.errors += 1
                continue

            output_hashes.add(candidate.sha256)
            summary.copied += 1
            if candidate.photo_date.date_token == "unknown_date":
                summary.unknown_date += 1
                status = "UNKNOWN_DATE"
            else:
                status = "COPIED"
            print(
                f"{status}: {display_path(candidate.path)} -> "
                f"{display_path(destination)}"
            )


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


def display_path(path: Path) -> str:
    project_dir = Path(__file__).resolve().parent
    try:
        return str(path.relative_to(project_dir))
    except ValueError:
        return str(path)


def print_unsupported(paths: list[Path], summary: Summary) -> None:
    for path in paths:
        print(f"SKIPPED_UNSUPPORTED: {display_path(path)}")
        summary.unsupported_skipped += 1


def print_summary(summary: Summary) -> None:
    print(f"Copied: {summary.copied}")
    print(f"Duplicates skipped: {summary.duplicates_skipped}")
    print(f"Unknown date: {summary.unknown_date}")
    print(f"Unsupported skipped: {summary.unsupported_skipped}")
    print(f"Errors: {summary.errors}")


def main() -> int:
    args = parse_args()
    exiftool = ensure_exiftool()
    project_dir = Path(__file__).resolve().parent
    input_dir = project_dir / "input"
    output_dir = project_dir / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    summary = Summary()
    supported, unsupported = discover_input_files(input_dir)
    print_unsupported(unsupported, summary)
    output_hashes = existing_output_hashes(output_dir, summary)
    candidates = collect_candidates(supported, output_hashes, exiftool, summary)
    groups = group_candidates(candidates, args.photographer, args.location)
    copy_candidates(groups, output_dir, output_hashes, summary)
    print_summary(summary)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
