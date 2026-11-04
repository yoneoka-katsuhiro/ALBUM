# Third-party software / 第三者ソフトウェア

ALBUM's own source is MIT licensed. The following components retain their own licenses.

- **Python**: Python Software Foundation License and notices. A standalone package includes the runtime and `third_party_licenses/PYTHON_LICENSE.txt`. The builder's distribution notices are also copied when available.
- **PyInstaller**: GPL with a bootloader exception permitting distribution of bundled applications under their own licenses. [License and exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt). PyInstaller is a build tool; its bootloader is in the executable.
- **ExifTool 13.55**, copyright Phil Harvey: distributed under the same terms as Perl (Artistic License or GPL). The bundled `exiftool/README` records these terms, `exiftool/html` contains the upstream documentation, and the Perl modules retain their notices. The Windows archive also includes the upstream launcher and Perl runtime files with their accompanying notices. [Upstream source and license](https://github.com/exiftool/exiftool/tree/13.55).
- **Pillow, pytest, and Ruff** are used to create test fixtures, run tests, or check source. They are not required by, or intentionally bundled into, the ALBUM runtime.

The build preserves the upstream Windows ExifTool directory in full. Do not distribute only its launcher, and do not remove license notices. ALBUM does not claim authorship of these components. The macOS build uses system Perl, which is not copied into the archive.

`third_party_licenses/PERL_ARTISTIC.txt` supplies the Artistic License for ExifTool. `PYINSTALLER_COPYING.txt` is copied from the installed build tool. Builds made with Conda also collect each bundled native library's notices from the exact installed package cache; missing notices fail the build. This includes OpenSSL, zlib, bzip2, xz/liblzma, libmpdec, and Expat when present. Other Python distributions retain their accompanying notices.

同梱ソフトウェアのライセンスはALBUMのMITライセンスに置き換わりません。写真・GPSログにもソフトウェアのライセンスを適用しません。
