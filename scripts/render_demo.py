"""Render the actual integration result; this is a report, not a GUI mockup."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from smoke_test import ROOT, exercise


def font(size: int):
    for path in ("/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def main() -> None:
    exiftool = shutil.which("exiftool")
    if not exiftool:
        raise SystemExit("ExifTool is required")
    with tempfile.TemporaryDirectory(prefix="album-demo-") as temporary:
        project = Path(temporary)
        transcript = exercise(
            project,
            [sys.executable, str(ROOT / "album.py")],
            exiftool,
            unicode_filenames=False,
        )
        transcript = transcript.replace(str(project), "<demo>")
        (ROOT / "docs" / "demo-log.txt").write_text(transcript, encoding="utf-8")
        demo = ROOT / "demo"
        for folder in ("input_image", "input_gps"):
            shutil.copytree(project / folder, demo / folder, dirs_exist_ok=True)
        canvas = Image.new("RGB", (1240, 890), "#f6f7f2")
        draw = ImageDraw.Draw(canvas)
        draw.text((48, 36), "ALBUM 0.3.0", font=font(34), fill="#183e34")
        draw.text((48, 90), "Actual JPEG + GPX integration result", font=font(22), fill="#43594f")
        draw.text(
            (48, 128),
            "Synthetic image and coordinates / no personal photographs",
            font=font(16),
            fill="#596a61",
        )
        before = Image.open(project / "input_image" / "sample.jpg")
        after = Image.open(project / "output" / "20260102_field" / "20260102_demo0001_field.jpg")
        for x, image, label in (
            (48, before, "INPUT  sample.jpg"),
            (650, after, "OUTPUT  20260102_demo0001_field.jpg"),
        ):
            draw.text((x, 181), label, font=font(16), fill="#183e34")
            canvas.paste(image.resize((540, 354)), (x, 215))
        draw.text((48, 586), "Original bytes unchanged", font=font(18), fill="#183e34")
        draw.text((650, 586), "GPS: 35.0010000, 139.0010000", font=font(18), fill="#183e34")
        draw.rounded_rectangle((48, 636, 1190, 829), radius=12, fill="#183e34")
        first, second = transcript.split("SECOND RUN", 1)
        summary_keys = ("Copied:", "Duplicates skipped:", "GPS coordinates added:", "Errors:")
        for x, part, title in ((72, first, "FIRST RUN"), (650, second, "SECOND RUN")):
            lines = [line for line in part.splitlines() if line.startswith(summary_keys)]
            draw.text((x, 653), title, font=font(17), fill="#e0c981")
            for i, line in enumerate(lines):
                draw.text((x, 687 + 29 * i), line, font=font(17), fill="#f6f7f2")
        draw.text(
            (48, 850),
            "Source: scripts/smoke_test.py  |  Full output: docs/demo-log.txt",
            font=font(15),
            fill="#596a61",
        )
        canvas.save(ROOT / "docs" / "images" / "demo-output.png")


if __name__ == "__main__":
    main()
