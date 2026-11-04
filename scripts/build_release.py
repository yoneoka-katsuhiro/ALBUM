"""Build on the target OS; bundle pinned ExifTool and all Python runtime files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXIFTOOL_VERSION = "13.55"
ARCHIVES = {
    "source": (
        "Image-ExifTool-13.55.tar.gz",
        "5f4c81d34ad406538c2871ad72dbfceb5d9b412b2f16cbbeb4d712d270846667",
    ),
    "windows": (
        "exiftool-13.55_64.zip",
        "9fadaf5221dcb07a5d018e21c8529e257917d2fad1fdfc8e64855c4fb73293df",
    ),
}


def copy_runtime_licenses(package: Path) -> None:
    """Retain notices for the builder's Python distribution and bundled libraries."""
    destination = package / "third_party_licenses"
    shutil.copytree(ROOT / "third_party_licenses", destination, dirs_exist_ok=True)
    pyinstaller = distribution("pyinstaller")
    for file in pyinstaller.files or []:
        if str(file).endswith("licenses/COPYING.txt"):
            shutil.copy2(pyinstaller.locate_file(file), destination / "PYINSTALLER_COPYING.txt")
    base = Path(sys.base_prefix)
    conda_metadata = base / "conda-meta"
    if conda_metadata.is_dir():
        binary_names = {file.name for file in (package / "_internal").iterdir()}
        for metadata in conda_metadata.glob("*.json"):
            record = json.loads(metadata.read_text())
            if any(Path(file).name in binary_names for file in record.get("files", [])):
                licenses = base / "pkgs" / metadata.stem / "info" / "licenses"
                if not licenses.is_dir():
                    raise RuntimeError(f"Missing license notices for {metadata.stem}")
                shutil.copytree(licenses, destination / metadata.stem, dirs_exist_ok=True)
    else:
        for source in (base / "LICENSE.txt", base / "LICENSE"):
            if source.is_file():
                shutil.copy2(source, destination / "PYTHON_DISTRIBUTION_LICENSE.txt")
                break


def fetch_archive(kind: str, cache: Path) -> Path:
    name, expected = ARCHIVES[kind]
    path = cache / name
    if not path.exists():
        url = "https://downloads.sourceforge.net/project/exiftool/" + name
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError(f"Checksum mismatch: {path}; remove it and download again")
    return path


def bundle_exiftool(destination: Path, cache: Path) -> None:
    source = fetch_archive("source", cache)
    extracted = cache / "source"
    extracted.mkdir(exist_ok=True)
    with tarfile.open(source) as archive:
        archive.extractall(extracted, filter="data")
    perl_source = extracted / f"Image-ExifTool-{EXIFTOOL_VERSION}"
    if sys.platform == "win32":
        windows = fetch_archive("windows", cache)
        extracted_windows = cache / "windows"
        with zipfile.ZipFile(windows) as archive:
            archive.extractall(extracted_windows)
        launcher = next(extracted_windows.rglob("exiftool(-k).exe"))
        shutil.copytree(launcher.parent, destination)
        (destination / "exiftool(-k).exe").rename(destination / "exiftool.exe")
    else:
        destination.mkdir()
        shutil.copy2(perl_source / "exiftool", destination / "exiftool")
        shutil.copytree(perl_source / "lib", destination / "lib")
        (destination / "exiftool").chmod(0o755)
    for name in ("README", "Changes", "perl-Image-ExifTool.spec"):
        candidate = perl_source / name
        if candidate.is_file():
            shutil.copy2(candidate, destination / name)
    shutil.copytree(perl_source / "html", destination / "html", dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-cache", type=Path, default=ROOT / "vendor")
    args = parser.parse_args()
    cache = args.archive_cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(build_dir / "pyinstaller-cache"))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--console",
            "--name",
            "album",
            "--specpath",
            str(build_dir),
            "album.py",
        ],
        check=True,
        env=env,
    )
    package = ROOT / "dist" / "album"
    bundle_exiftool(package / "exiftool", cache)
    for name in (
        "README.md",
        "README-ja.md",
        "LICENSE",
        "VERSION.txt",
        "CHANGELOG.md",
        "CITATION.cff",
        "THIRD_PARTY_NOTICES.md",
    ):
        shutil.copy2(ROOT / name, package / name)
    shutil.copytree(ROOT / "docs", package / "docs", dirs_exist_ok=True)
    shutil.copytree(
        ROOT / "demo", package / "demo", dirs_exist_ok=True, ignore=shutil.ignore_patterns("output")
    )
    for name in ("input_image", "input_gps", "output"):
        (package / name).mkdir(exist_ok=True)
    copy_runtime_licenses(package)
    metadata = {
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "exiftool": EXIFTOOL_VERSION,
        "dependencies": subprocess.check_output(
            [sys.executable, "-m", "pip", "freeze"], text=True
        ).splitlines(),
    }
    (package / "BUILD_INFO.json").write_text(json.dumps(metadata, indent=2) + "\n")
    version = (ROOT / "VERSION.txt").read_text().strip()
    system = "Windows" if sys.platform == "win32" else "macOS"
    arch = "x64" if platform.machine().lower() in {"x86_64", "amd64"} else "arm64"
    name = f"ALBUM-{version}-{system}-{arch}"
    archive = Path(shutil.make_archive(str(ROOT / "dist" / name), "zip", ROOT / "dist", "album"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
    print(archive)


if __name__ == "__main__":
    main()
