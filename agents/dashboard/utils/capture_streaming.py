"""Pure helpers used by the Capture Studio MJPEG stream."""

from collections.abc import Iterator
from typing import BinaryIO, Mapping, Any


def iter_jpeg_frames(stdout: BinaryIO) -> Iterator[bytes]:
    """Yield complete JPEG frames from a chunked ffmpeg byte stream."""
    buffer = b""
    while True:
        chunk = stdout.read(65536)
        if not chunk:
            break
        buffer += chunk
        while True:
            start = buffer.find(b"\xff\xd8")
            if start == -1:
                buffer = buffer[-4:] if len(buffer) > 4 else buffer
                break
            end = buffer.find(b"\xff\xd9", start + 2)
            if end == -1:
                if start:
                    buffer = buffer[start:]
                break
            yield buffer[start : end + 2]
            buffer = buffer[end + 2 :]


def resolve_adb_serial(session: Mapping[str, Any]) -> str:
    """Return the Capture session's preferred ADB device identifier."""
    return str(session.get("udid") or session.get("device_name") or "")
