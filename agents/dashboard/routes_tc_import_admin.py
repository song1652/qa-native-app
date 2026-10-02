"""TC Studio access to shared mapping profiles and durable md history."""
from __future__ import annotations

import re
import secrets
import json
from datetime import datetime

import _paths
from dash_http import _read_body, _read_profiles_locked, _update_profiles_locked

ADMIN_ROUTES = [(method, re.compile(path + r'\Z'), handler) for method, path, handler in [
    ('POST', r'/api/tc-library/import/mapping-profiles', '_tci_create_profile'),
    ('PUT', r'/api/tc-library/import/mapping-profiles/(?P<profile_id>[\w-]+)', '_tci_update_profile'),
    ('DELETE', r'/api/tc-library/import/mapping-profiles/(?P<profile_id>[\w-]+)', '_tci_delete_profile'),
    ('GET', r'/api/tc-library/import/md-runs', '_tci_md_runs'),
    ('GET', r'/api/tc-library/import/md-runs/(?P<run_id>[\w-]+)', '_tci_md_run'),
    ('POST', r'/api/tc-library/import/md-runs/(?P<run_id>[\w-]+)/rollback', '_tci_md_rollback'),
]]


class ImportRunError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code

FIELD_NAMES = {'feature': 'title', 'l1': 'group', 'source_tc_id': 'tc_id'}
FIELDS = {'feature', 'steps', 'expected', 'precondition', 'priority', 'l1', 'l2', 'l3', 'source_tc_id', 'tags', 'note'}


def _call(fn, *args):
    from _tc_library import LibraryError
    try:
        return fn(*args)
    except ImportRunError as exc:
        status = 404 if exc.code.endswith('_NOT_FOUND') else 409 if exc.code in {
            'PROFILE_EXISTS', 'ROLLBACK_CONFLICT', 'RECOVERY_CONFLICT', 'TARGET_CHANGED', 'COMMIT_LOCKED'} else 500 if exc.code in {
            'PROFILE_STORE_ERROR', 'RUN_CORRUPT', 'SNAPSHOT_CORRUPT', 'ROLLBACK_VERIFICATION_FAILED'} else 400
        raise LibraryError(str(exc), exc.code, status) from exc


def _admin_body(handler):
    from _tc_library import LibraryError
    try:
        return _read_body(handler)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LibraryError('올바른 JSON 본문이 필요합니다', 'INVALID_JSON') from exc


def _public_profile(profile):
    reverse = {v: k for k, v in FIELD_NAMES.items()}
    columns = {reverse.get(k, k): v.replace('열', '').strip().upper()
               for k, v in profile.get('mappings', {}).items()
               if reverse.get(k, k) in FIELDS and isinstance(v, str) and v}
    mapping = {'header_row': profile.get('header_row', 1), 'columns': columns}
    return {'id': profile['id'], 'name': profile['name'], 'mapping': mapping, 'columns': columns}


def _validated(body):
    from _tc_library import LibraryError
    from openpyxl.utils.cell import column_index_from_string
    if not isinstance(body, dict):
        raise LibraryError('프로필 객체가 필요합니다', 'INVALID_PROFILE')
    name, mapping = body.get('name'), body.get('mapping')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 50 or not isinstance(mapping, dict):
        raise LibraryError('이름과 매핑을 확인하세요', 'INVALID_PROFILE')
    header = mapping.get('header_row', 1)
    columns = mapping.get('columns')
    if (type(header) is not int or not 1 <= header <= 1048576
            or not isinstance(columns, dict) or not {'feature', 'steps', 'expected'} <= columns.keys()):
        raise LibraryError('헤더 행·필수 열을 확인하세요', 'INVALID_PROFILE')
    normalized = {}
    for key, value in columns.items():
        if key == 'auto':
            continue
        if key not in FIELDS or not isinstance(value, str):
            raise LibraryError('지원하지 않는 열 매핑입니다', 'INVALID_PROFILE')
        value = value.strip().upper()
        if not value and key not in {'feature', 'steps', 'expected'}:
            continue
        if not re.fullmatch('[A-Z]{1,3}', value) or column_index_from_string(value) > 16384:
            raise LibraryError('Excel 열 이름을 확인하세요', 'INVALID_PROFILE')
        normalized[FIELD_NAMES.get(key, key)] = value + '열'
    return {'name': name.strip(), 'mappings': normalized, 'header_row': header}


def _public_run(run, details=False):
    keys = ('run_id', 'status', 'created_at', 'committed_at', 'rolled_back_at', 'summary', 'result',
            'rollback_result', 'tc_library_suite', 'snapshot_id')
    public = {k: run[k] for k in keys if k in run}
    public['source'] = 'tc-library-md' if run.get('tc_library_suite') else 'excel-md'
    public['sources'] = [{k: s[k] for k in ('file_id', 'file_name', 'sheet_name', 'header_row') if k in s}
                         for s in run.get('sources', []) if isinstance(s, dict)]
    if details:
        rowkeys = ('tc_id', 'title', 'group', 'status', 'reason_code', 'reason', 'excluded', 'decision', 'before', 'after')
        public['rows'] = [{**{k: r[k] for k in rowkeys if k in r},
                           'file_name': r.get('_source_file', ''), 'sheet_name': r.get('_source_sheet', ''),
                           'source_row': r.get('_row', 0)} for r in run.get('rows', [])]
    from _tc_library import without_auto
    return without_auto(public)


class TcImportAdminRoutesMixin:
    def _tci_profiles(self):
        data = _call(_read_profiles_locked, _paths.IMPORT_PROFILES_PATH)
        self._tcl_json({'ok': True, 'profiles': [_public_profile(p) for p in data.get('profiles', [])]})

    def _tci_save_profile(self, profile_id=None):
        values = _validated(_admin_body(self))
        def mutate(data):
            profiles = data.setdefault('profiles', [])
            target = next((p for p in profiles if p.get('id') == profile_id), None) if profile_id else None
            if profile_id and target is None:
                raise ImportRunError('프로필을 찾을 수 없습니다', 'PROFILE_NOT_FOUND')
            if any(p is not target and p.get('name') == values['name'] for p in profiles):
                raise ImportRunError('같은 이름의 프로필이 있습니다', 'PROFILE_EXISTS')
            if target is None:
                target = {'id': 'prof_' + secrets.token_hex(4), 'created_at': datetime.now().isoformat()}
                profiles.append(target)
            target.update(values, updated_at=datetime.now().isoformat())
            return dict(target)
        profile = _call(_update_profiles_locked, _paths.IMPORT_PROFILES_PATH, mutate)
        self._tcl_json({'ok': True, 'profile': _public_profile(profile)}, 200 if profile_id else 201)

    def _tci_create_profile(self):
        self._tci_save_profile()

    def _tci_update_profile(self, profile_id):
        self._tci_save_profile(profile_id)

    def _tci_delete_profile(self, profile_id):
        _admin_body(self)
        def mutate(data):
            profiles = data.get('profiles', [])
            if not any(p.get('id') == profile_id for p in profiles):
                raise ImportRunError('프로필을 찾을 수 없습니다', 'PROFILE_NOT_FOUND')
            data['profiles'] = [p for p in profiles if p.get('id') != profile_id]
            return profile_id
        _call(_update_profiles_locked, _paths.IMPORT_PROFILES_PATH, mutate)
        self._tcl_json({'ok': True, 'deleted': profile_id})

    def _tci_md_runs(self):
        from _state import read_state
        runs = [read_state(path) for path in _paths.TC_LIBRARY_DIR.glob('*/md_runs/run_*.json')]
        self._tcl_json({'ok': True, 'runs': [_public_run(run) for run in runs], 'errors': []})

    def _tci_md_run(self, run_id):
        from _state import read_state
        from _tc_library import LibraryError
        matches = list(_paths.TC_LIBRARY_DIR.glob(f'*/md_runs/{run_id}.json')) if re.fullmatch(r'run_[0-9a-f]{12}', run_id) else []
        if not matches:
            raise LibraryError('작업을 찾을 수 없습니다', 'RUN_NOT_FOUND', 404)
        self._tcl_json({'ok': True, **_public_run(read_state(matches[0]), True)})

    def _tci_md_rollback(self, run_id):
        from _tc_md_export import rollback
        _admin_body(self)
        from _tc_library import LibraryError
        matches = list(_paths.TC_LIBRARY_DIR.glob(f'*/md_runs/{run_id}.json')) if re.fullmatch(r'run_[0-9a-f]{12}', run_id) else []
        if not matches:
            raise LibraryError('작업을 찾을 수 없습니다', 'RUN_NOT_FOUND', 404)
        result = rollback(matches[0].parents[1].name, run_id)
        self._tcl_json({'ok': True, **result})
