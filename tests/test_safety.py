from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import album


@pytest.mark.parametrize("offset", ["+24:00", "+09:60", "JST", ""])
def test_bad_utc_offset_rejected(offset):
    with pytest.raises(album.argparse.ArgumentTypeError):
        album.parse_utc_offset(offset)


def test_gap_boundary_and_outside():
    timestamp = datetime(2026, 1, 1)
    point = album.GPSPoint(timestamp, 35, 139, "demo")
    assert album.coordinate_for_time(
        [point], [timestamp], timestamp + timedelta(seconds=300), 300
    ) == (35, 139)
    assert (
        album.coordinate_for_time([point], [timestamp], timestamp + timedelta(seconds=301), 300)
        is None
    )


def test_write_failure_preserves_target_and_removes_temporary_file(tmp_path):
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"irreplaceable")
    with patch.object(album, "_write_gps_tags", side_effect=RuntimeError("failed")):
        with pytest.raises(RuntimeError):
            album.write_gps_tags("exiftool", target, 35, 139)
    assert target.read_bytes() == b"irreplaceable"
    assert list(tmp_path.iterdir()) == [target]


def test_gps_readback_mismatch_preserves_target(tmp_path):
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"irreplaceable")
    info = album.GeotagPhotoInfo(target, None, 0, 0)
    with (
        patch.object(album, "_write_gps_tags"),
        patch.object(album, "read_geotag_photo_info", return_value=info),
    ):
        with pytest.raises(RuntimeError, match="read-back"):
            album.write_gps_tags("exiftool", target, 35, 139)
    assert target.read_bytes() == b"irreplaceable"


def test_changed_source_is_not_deleted_after_copy(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"original")
    candidate = album.PhotoCandidate(
        source, album.sha256_file(source), album.PhotoDate("20260101", datetime(2026, 1, 1))
    )
    real_copy = album.copy_and_verify

    def changed_copy(*args):
        result = real_copy(*args)
        source.write_bytes(b"new data")
        return result

    summary = album.Summary()
    with patch.object(album, "copy_and_verify", side_effect=changed_copy):
        album.copy_candidates(
            {("20260101", "demo", "field"): [candidate]}, tmp_path / "output", set(), summary, True
        )
    assert source.read_bytes() == b"new data"
    assert summary.input_deleted == 0
    assert summary.errors == 1


def test_nmea_header_does_not_override_camera_timezone(tmp_path):
    log = tmp_path / "route.log"
    log.write_text(
        "@Olympus +0900\n$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\n"
    )
    point = album.parse_nmea_log(log, timezone.utc)[0]
    assert point.timestamp == datetime(1994, 3, 23, 12, 35, 19)


def test_geotag_input_requires_geotag_flag():
    with pytest.raises(SystemExit) as exc:
        album.parse_args(["--photographer", "demo", "--geotag-input"])
    assert exc.value.code == 2


def test_sequence_limit_preserves_existing_names(tmp_path):
    candidate = album.PhotoCandidate(tmp_path / "a.jpg", "", album.PhotoDate("20260101", None))
    with pytest.raises(RuntimeError, match="9999"):
        album.next_available_destination(tmp_path, candidate, "demo", "field", 10000)
