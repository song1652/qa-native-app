"""Pure Capture streaming boundary tests."""

import io

from agents.dashboard.utils.capture_streaming import (
    iter_jpeg_frames,
    resolve_adb_serial,
)


class ChunkedReader:
    def __init__(self, chunks: list[bytes]):
        self._chunks = iter(chunks)

    def read(self, _size: int) -> bytes:
        return next(self._chunks, b"")


def test_iter_jpeg_frames_handles_noise_and_split_markers():
    reader = ChunkedReader([
        b"noise\xff",
        b"\xd8first\xff",
        b"\xd9junk\xff\xd8sec",
        b"ond\xff\xd9tail",
    ])

    assert list(iter_jpeg_frames(reader)) == [
        b"\xff\xd8first\xff\xd9",
        b"\xff\xd8second\xff\xd9",
    ]


def test_iter_jpeg_frames_ignores_incomplete_trailing_frame():
    reader = io.BytesIO(b"\xff\xd8complete\xff\xd9\xff\xd8incomplete")

    assert list(iter_jpeg_frames(reader)) == [b"\xff\xd8complete\xff\xd9"]


def test_resolve_adb_serial_prefers_udid_then_device_name():
    assert resolve_adb_serial({"udid": "R3CN", "device_name": "Pixel"}) == "R3CN"
    assert resolve_adb_serial({"device_name": "emulator-5554"}) == "emulator-5554"
    assert resolve_adb_serial({}) == ""
