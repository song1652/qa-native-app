"""Pure observability manifest and artifact rules."""

import struct

from tests.observability import runtime
from tests.observability.manifest import (
    append_attempt,
    mp4_duration_seconds,
    node_slug,
    should_keep,
)


def _mp4(timescale: int, duration: int) -> bytes:
    payload = (
        b"\x00\x00\x00\x00"
        + struct.pack(">I", 0)
        + struct.pack(">I", 0)
        + struct.pack(">I", timescale)
        + struct.pack(">I", duration)
    )
    mvhd = struct.pack(">I", 8 + len(payload)) + b"mvhd" + payload
    moov = struct.pack(">I", 8 + len(mvhd)) + b"moov" + mvhd
    return struct.pack(">I", 16) + b"ftyp" + b"isom0000" + moov


def test_node_slug_is_safe_and_bounded():
    value = node_slug("tests/generated/android/demo.py::test 한글 " + "x" * 240)

    assert len(value) <= 213
    assert "/" not in value
    assert "::" not in value
    assert " " not in value


def test_keep_policy_preserves_failure_and_flaky_pass():
    assert should_keep("on_failure", "failed") is True
    assert should_keep("on_failure", "passed") is False
    assert should_keep("on_failure", "passed", attempt_count=2) is True
    assert should_keep("never", "failed") is False


def test_append_attempt_updates_summary_without_discarding_history():
    manifest = {"entries": []}
    append_attempt(manifest, "node", "slug", {"n": 1, "outcome": "failed", "kept": True})
    append_attempt(manifest, "node", "slug", {"n": 2, "outcome": "passed", "kept": True})

    assert manifest["entries"][0]["attempt_count"] == 2
    assert manifest["entries"][0]["outcome"] == "passed"
    assert [item["n"] for item in manifest["entries"][0]["attempts"]] == [1, 2]


def test_mp4_duration_and_runtime_compatibility_aliases(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(_mp4(1000, 2500))

    assert mp4_duration_seconds(video) == 2.5
    assert runtime._should_keep is should_keep
    assert runtime._append_attempt is append_attempt
