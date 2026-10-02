"""Run-owned execution summaries; pipeline.json remains a latest-run view."""
import json
import os
import re
import tempfile
from pathlib import Path


def execution_result_path(root: Path, run_id: str) -> Path:
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', run_id):
        raise ValueError('Invalid run_id')
    return Path(root) / 'state' / 'runs' / run_id / 'execution_result.json'


def read_execution_result(root: Path, run_id: str) -> dict | None:
    try:
        data = json.loads(execution_result_path(root, run_id).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get('run_id') == run_id else None


def write_execution_result(root: Path, run_id: str, result: dict) -> dict:
    path = execution_result_path(root, run_id)
    if result.get('run_id', run_id) != run_id:
        raise ValueError('Execution result run_id mismatch')
    payload = {**result, 'run_id': run_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.execution_result-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return payload
