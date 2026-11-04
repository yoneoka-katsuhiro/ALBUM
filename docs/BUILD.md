# Build and verification / ビルドと検証

The runtime code uses Python's standard library and calls ExifTool. Pillow, pytest, Ruff, and PyInstaller are development tools, not application dependencies. Python 3.11+ can run the source; the release workflow uses Python 3.12 on macOS 26 ARM64 and Windows Server 2022 x64.

実行コードはPython標準ライブラリとExifToolを使います。Pillowなどは検証・配布作成用です。Windows版はWindows上、macOS版はmacOS上で作成します。クロスコンパイルは行いません。

## Development environment

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python scripts/smoke_test.py
```

The last command requires ExifTool in PATH. It creates a temporary synthetic JPEG and GPX, runs the real CLI twice, checks interpolated coordinates, compares original SHA-256 and decoded pixels, and verifies duplicate handling. Both the directory and JPEG filenames contain spaces and Japanese characters; the filenames also contain an accented Latin character. It does not process personal data.

最後のコマンドは実際のExifToolを使い、合成JPEG・GPXを一時フォルダーで処理します。座標、原本ハッシュ、デコード画素、再実行時の重複除外を検証します。個人の写真は使いません。

## Create a package

```bash
python scripts/build_release.py
```

The script downloads ExifTool 13.55 from the project's SourceForge distribution, verifies SHA-256 values against the pinned official checksums, and bundles its Perl source on macOS or Windows executable and Perl files on Windows. The source checksum is `5f4c81d34ad406538c2871ad72dbfceb5d9b412b2f16cbbeb4d712d270846667`; the Windows x64 checksum is `9fadaf5221dcb07a5d018e21c8529e257917d2fad1fdfc8e64855c4fb73293df`. Source: [official distribution checksums](https://sourceforge.net/projects/exiftool/files/checksums-13.55.txt/download).

Existing archives in `vendor` are reused only after checksum verification. An offline cache can be selected with `--archive-cache PATH`. Do not replace an archive without reviewing its version, checksum, license, and compatibility. macOS uses `/usr/bin/env perl` from the operating system; Python is bundled. Windows includes ExifTool's own Perl runtime. See [ExifTool's installation instructions](https://github.com/exiftool/exiftool/blob/13.55/html/install.html).

The generated `dist/album` directory includes the executable, `_internal`, ExifTool, manuals, licenses, empty data folders, and `BUILD_INFO.json`. The ZIP filename identifies version, OS, and architecture. A matching `.zip.sha256` file records its digest. Build metadata records the source commit and whether tracked or untracked changes were present, plus Python, platform, architecture, ExifTool, and the installed build packages. If Git metadata is unavailable, the commit is `unavailable` and the change state is `null`.

ExifTool calls send an explicitly UTF-8 argument file through standard input using `-charset filename=UTF8 -@ -`. This avoids Windows command-line code-page conversion for Japanese paths. ALBUM also writes UTF-8 console/redirected logs without changing the operating system code page. See the [official ExifTool Windows filename documentation](https://exiftool.org/exiftool_pod.html#WINDOWS-UNICODE-FILE-NAMES).

macOS verification:

```bash
python scripts/smoke_test.py --executable dist/album/album --exiftool dist/album/exiftool/exiftool
```

Windows verification:

```powershell
python scripts/smoke_test.py --executable dist/album/album.exe --exiftool dist/album/exiftool/exiftool.exe
```

## CI and release

GitHub Actions runs lint, formatting, regressions, package creation, and the real-image smoke test on both systems. It uploads archives only after the packaged executable passes. The workflow supports push, pull request, and manual dispatch. It does not publish releases automatically. Inspect the completed run and package contents before attaching assets to a versioned GitHub Release.

CIは両OSでコード検査・回帰テスト・実行ファイル生成・実JPEG処理を行い、成功したZIPとハッシュを保存します。リリース公開は自動化していません。CI成功だけで、実機Windows 10/11や全カメラ形式での操作検証まで済んだとは扱いません。

Unsigned Windows and ad-hoc-signed macOS development artifacts may trigger OS warnings. These are not notarized or Authenticode-signed installers. No system security setting is changed by the build or application. Intel Mac packages are not currently built.

The build follows [PyInstaller's one-folder distribution workflow](https://www.pyinstaller.org/en/stable/usage.html). Reproducible configuration is provided, but byte-identical ZIP reproduction is not claimed: native toolchains, timestamps, and Python patch versions can change the artifact hash.
