"""Capture MCP must use the driver pinned to the active session's target."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "agents" / "dashboard"))
import shared
from routes import mcp
from utils import capture_driver


@pytest.mark.parametrize("actual_udid", ["usb-old-phone", "emulator-5554"])
def test_mcp_tap_only_reaches_current_capture_identity(monkeypatch, actual_udid):
    session = {"session_id": "current", "active": True, "platform": "android",
               "target": "emulator", "udid": "emulator-5554", "actions": []}
    driver = SimpleNamespace(capabilities={"udid": actual_udid}, tap=Mock())
    monkeypatch.setattr(shared, "_capture_driver", driver)
    monkeypatch.setattr(mcp, "load_capture_session", lambda: session)
    monkeypatch.setattr(capture_driver, "load_capture_session", lambda: session)
    save = Mock()
    monkeypatch.setattr(mcp, "save_capture_session", save)
    monkeypatch.setattr(mcp, "broadcast_timeline_sync", Mock())

    ok, result = mcp._run_tool("device_tap", {"x": 10, "y": 20})

    if actual_udid == session["udid"]:
        assert ok and result["ok"]
        driver.tap.assert_called_once_with([(10, 20)])
        assert save.call_args.args[0]["udid"] == session["udid"]
    else:
        assert not ok
        assert "not connected" in result
        driver.tap.assert_not_called()
        save.assert_not_called()
