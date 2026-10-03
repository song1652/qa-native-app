"""A failed snapshot replacement must keep the previous Capture draft intact."""
import json
from pathlib import Path

import pytest
from agents.dashboard.utils import state


def test_dashboard_tests_isolate_capture_session_from_workspace(tmp_path):
    from utils import state
    assert state.CAPTURE_SESSION_PATH.is_relative_to(tmp_path)


def test_capture_snapshot_failed_replace_keeps_previous_draft(tmp_path, monkeypatch):
    path = tmp_path / 'capture_session.json'
    before = {'session_id': 'draft', 'actions': [{'action': 'tap'}]}
    path.write_text(json.dumps(before))
    monkeypatch.setattr(state, 'CAPTURE_SESSION_PATH', path)
    def fail_replace(*args):
        raise OSError('replacement failed')
    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(OSError, match='replacement failed'):
        state.save_capture_session({'session_id': 'draft', 'actions': []})
    assert json.loads(path.read_text()) == before
    assert list(tmp_path.iterdir()) == [path]


def test_capture_snapshot_replaces_complete_json(tmp_path, monkeypatch):
    path = tmp_path / 'capture_session.json'
    monkeypatch.setattr(state, 'CAPTURE_SESSION_PATH', path)
    draft = {'session_id': 'draft', 'actions': [{'action': 'input', 'text': '입력'}]}
    state.save_capture_session(draft)
    assert state.load_capture_session() == draft
    assert list(tmp_path.iterdir()) == [path]
