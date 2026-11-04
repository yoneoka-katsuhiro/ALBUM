"""Exercise a real JPEG/GPX round trip with ExifTool and either source or frozen ALBUM."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def exercise(project: Path, command: list[str], exiftool: str) -> str:
    inputs = project / "input_image"
    gps = project / "input_gps"
    inputs.mkdir(parents=True)
    gps.mkdir()
    image = Image.new("RGB", (640, 420), "#edf3e8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((36, 36, 604, 384), fill="#1d5244")
    draw.ellipse((220, 110, 420, 310), fill="#d8b869")
    draw.text((64, 62), "ALBUM / SYNTHETIC JPEG FIXTURE", fill="white")
    photo = inputs / "sample.jpg"
    image.save(photo, quality=92)
    run(
        [
            exiftool,
            "-overwrite_original",
            "-DateTimeOriginal=2026:01:02 09:00:05",
            "-OffsetTimeOriginal=+09:00",
            str(photo),
        ]
    )
    original = photo.read_bytes()
    (inputs / "duplicate.jpg").write_bytes(original)
    (gps / "route.gpx").write_text(
        """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="35.0" lon="139.0"><time>2026-01-02T00:00:00Z</time></trkpt>
<trkpt lat="35.002" lon="139.002"><time>2026-01-02T00:00:10Z</time></trkpt>
</trkseg></trk></gpx>""",
        encoding="utf-8",
    )
    arguments = [
        "--project-dir",
        str(project),
        "--photographer",
        "demo",
        "--location",
        "field",
        "--geotag",
        "--gps-timezone",
        "+09:00",
    ]
    first = run(command + arguments)
    assert "Copied: 1" in first and "Duplicates skipped: 1" in first
    assert "GPS coordinates added: 1" in first and "Errors: 0" in first
    target = project / "output" / "20260102_field" / "20260102_demo0001_field.jpg"
    tags = json.loads(run([exiftool, "-json", "-n", "-GPSLatitude", "-GPSLongitude", str(target)]))[
        0
    ]
    assert abs(tags["GPSLatitude"] - 35.001) < 0.000001
    assert abs(tags["GPSLongitude"] - 139.001) < 0.000001
    with Image.open(photo) as before, Image.open(target) as after:
        assert before.tobytes() == after.tobytes(), "Decoded image pixels changed"
    assert photo.read_bytes() == original, "Input original changed"
    second = run(command + arguments)
    assert "Copied: 0" in second and "Duplicates skipped: 2" in second
    report = target.parent / "album_gps.csv"
    assert "output/20260102_field/20260102_demo0001_field.jpg" in report.read_text().replace(
        "\\", "/"
    )
    result = first + "\nSECOND RUN\n" + second
    result += "\nVerified: original SHA-256 " + hashlib.sha256(original).hexdigest() + "\n"
    result += "Verified: GPS 35.001, 139.001; unchanged decoded pixels; idempotent second run.\n"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--exiftool", type=Path)
    parser.add_argument("--project-dir", type=Path)
    args = parser.parse_args()
    command = (
        [str(args.executable.resolve())]
        if args.executable
        else [sys.executable, str(ROOT / "album.py")]
    )
    exiftool = str(args.exiftool.resolve()) if args.exiftool else shutil.which("exiftool")
    if not exiftool:
        raise SystemExit("ExifTool is required for this integration test")
    if args.project_dir:
        print(exercise(args.project_dir.resolve(), command, exiftool))
    else:
        with tempfile.TemporaryDirectory(prefix="ALBUM smoke 日本語 ") as folder:
            print(exercise(Path(folder), command, exiftool))


if __name__ == "__main__":
    main()
