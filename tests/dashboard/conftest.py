"""Dashboard tests must never replace the user's Capture draft."""
import sys

import pytest


@pytest.fixture(autouse=True)
def isolate_capture_session(tmp_path, monkeypatch):
    # Both import spellings exist in these tests and each holds its own path.
    for name in ('shared', 'utils.state', 'agents.dashboard.shared', 'agents.dashboard.utils.state'):
        module = sys.modules.get(name)
        if module is not None:
            monkeypatch.setattr(module, 'CAPTURE_SESSION_PATH', tmp_path / 'capture_session.json')
