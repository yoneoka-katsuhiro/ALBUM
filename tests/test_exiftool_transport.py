import json
import subprocess
from unittest.mock import patch

import pytest

import album


def test_unicode_metadata_path_bypasses_native_code_page():
    path = album.Path(r"C:\Users\研究者\写真 folder\標本 #1.jpg")

    def windows_launcher(argv, **kwargs):
        # Emulate a Windows launcher whose native argv code page cannot encode
        # Japanese. Filename bytes must arrive through ExifTool's argument file.
        assert all(arg.isascii() for arg in argv[1:])
        assert argv[1:] == ["-charset", "filename=UTF8", "-@", "-"]
        assert kwargs["encoding"] == "utf-8"
        args = kwargs["input"].encode("utf-8").decode("utf-8").splitlines()
        assert str(path) in args
        assert "-DateTimeOriginal" in args
        return subprocess.CompletedProcess(
            argv, 0, json.dumps([{"DateTimeOriginal": "2026:01:02 09:00:05"}]), ""
        )

    with patch.object(album.subprocess, "run", side_effect=windows_launcher):
        assert album.read_photo_date("exiftool.exe", path).date_token == "20260102"


@pytest.mark.parametrize("separator", ["\n", "\r", "\0"])
def test_argument_file_control_characters_cannot_inject_options(separator):
    with patch.object(album.subprocess, "run") as run:
        with pytest.raises(RuntimeError, match="control characters"):
            album.run_exiftool(
                ["exiftool", "-json", "photo" + separator + "-delete_original!b.jpg"]
            )
    run.assert_not_called()
