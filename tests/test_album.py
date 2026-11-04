import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import album


def test_copy_never_overwrites_existing_file(tmp_path):
    source, target = tmp_path / "source.jpg", tmp_path / "target.jpg"
    source.write_bytes(b"new")
    target.write_bytes(b"irreplaceable")
    with pytest.raises(FileExistsError):
        album.copy_and_verify(source, target, album.sha256_file(source))
    assert target.read_bytes() == b"irreplaceable"


def test_failed_verification_removes_only_new_copy(tmp_path):
    source, target = tmp_path / "source.jpg", tmp_path / "target.jpg"
    source.write_bytes(b"changed")
    assert not album.copy_and_verify(source, target, hashlib.sha256(b"old").hexdigest())
    assert source.read_bytes() == b"changed"
    assert not target.exists()


def test_nmea_invalid_minutes_rejected():
    assert album.parse_nmea_coordinate("3560.00", "N") is None
    assert album.parse_nmea_coordinate("13999.00", "E") is None


def test_nmea_bad_checksum_rejected():
    assert (
        album.parse_rmc_sentence(
            "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*00",
            timezone.utc,
            "test.log",
        )
        is None
    )


def test_nmea_valid_checksum_and_subseconds():
    p = album.parse_rmc_sentence(
        "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A",
        timezone.utc,
        "test.log",
    )
    assert p.timestamp == datetime(1994, 3, 23, 12, 35, 19)
    assert p.latitude == pytest.approx(48.1173)
    assert album.parse_nmea_datetime("123519.25", "230394", timezone.utc).microsecond == 250000


def test_interpolation_crosses_antimeridian():
    start = datetime(2026, 1, 1)
    points = [
        album.GPSPoint(start, 10, 179, "a"),
        album.GPSPoint(start + timedelta(seconds=10), 10, -179, "a"),
    ]
    lat, lon = album.coordinate_for_time(
        points, [p.timestamp for p in points], start + timedelta(seconds=5), 10
    )
    assert lat == 10
    assert abs(lon) == 180


def test_do_not_interpolate_between_unrelated_logs():
    start = datetime(2026, 1, 1)
    points = [
        album.GPSPoint(start, 10, 100, "a"),
        album.GPSPoint(start + timedelta(seconds=10), 20, 110, "b"),
    ]
    assert album.coordinate_for_time(
        points, [p.timestamp for p in points], start + timedelta(seconds=3), 10
    ) == (10, 100)


def test_gps_requires_capture_time_not_file_mtime():
    assert album.metadata_datetime({"FileModifyDate": "2026:01:01 12:00:00"}) is None


def test_gps_honors_camera_offset():
    assert album.metadata_datetime(
        {"DateTimeOriginal": "2026:01:01 09:00:00", "OffsetTimeOriginal": "+09:00"},
        timezone.utc,
    ) == datetime(2026, 1, 1)


def test_photo_discovery_ignores_symlinks(tmp_path):
    source = tmp_path / "outside.jpg"
    source.write_bytes(b"photo")
    folder = tmp_path / "input_image"
    folder.mkdir()
    try:
        (folder / "link.jpg").symlink_to(source)
    except OSError:
        pytest.skip("Symlink creation requires platform permission")
    assert album.discover_input_files(folder) == ([], [])


def test_geotag_does_not_target_input_by_default(tmp_path):
    inputs, outputs, logs = [tmp_path / n for n in ("input_image", "output", "input_gps")]
    for folder in (inputs, outputs, logs):
        folder.mkdir()
    original = inputs / "photo.jpg"
    original.write_bytes(b"original")
    point = album.GPSPoint(datetime(2026, 1, 1), 35, 139, "demo")
    with (
        patch.object(album, "parse_gps_points", return_value=[point]),
        patch.object(album, "read_geotag_photo_info") as read,
    ):
        album.geotag_images(
            tmp_path, inputs, logs, outputs, "exiftool", timezone.utc, 300, album.Summary()
        )
    read.assert_not_called()
    assert original.read_bytes() == b"original"


def test_repeat_import_recognizes_geotagged_copy(tmp_path):
    source = tmp_path / "original.jpg"
    output = tmp_path / "output"
    target = output / "date" / "photo.jpg"
    source.write_bytes(b"original")
    original_hash = album.sha256_file(source)
    assert album.copy_and_verify(source, target, original_hash)
    album.record_copy_provenance(target, original_hash)
    target.write_bytes(b"original plus GPS")
    album.refresh_copy_provenance(target, original_hash)
    assert original_hash in album.existing_output_hashes(output, album.Summary())
    target.write_bytes(b"unrelated external edit")
    assert original_hash not in album.existing_output_hashes(output, album.Summary())
    changed_hash = album.sha256_file(target)
    target.write_bytes(b"unrelated external edit plus GPS")
    album.refresh_copy_provenance(target, changed_hash)
    assert original_hash not in album.existing_output_hashes(output, album.Summary())
