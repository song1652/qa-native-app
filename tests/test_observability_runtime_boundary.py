"""Observability runtime/facade compatibility boundary."""

import importlib


def test_legacy_observability_import_aliases_runtime_module():
    legacy = importlib.import_module("tests._observability")
    runtime = importlib.import_module("tests.observability.runtime")

    assert legacy is runtime
    for name in ("session_start", "start", "capture_screenshot", "stop", "session_finish"):
        assert callable(getattr(runtime, name))
