"""Durable execution history with run results taking precedence over artifacts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from threading import Lock

_LOCK = Lock()
_RUN_ID = re.compile(r'run_(android|ios)_\d{8}_\d{6}_\d{3}')
_REPORT_NAME = re.compile(r'report_(?:(android|ios)_)?(\d{8}_\d{6})(?:_(\d{3}))?\.html$')


def _now():
    return datetime.now(timezone.utc)


def _date(value):
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


class _ReportSummary(HTMLParser):
    """Read the existing report template's labeled statistics and group names."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.stats = {}
        self.groups = []
        self.created = None
        self.number = None
        self.title = ''
        self.run_id = None

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            metadata = dict(attrs)
            if metadata.get('name') == 'qa-run-id' and _RUN_ID.fullmatch(metadata.get('content', '')):
                self.run_id = metadata['content']
        if tag in {'meta', 'link', 'input', 'img', 'br', 'hr', 'source', 'wbr'}:
            return
        classes = dict(attrs).get('class', '').split()
        capture = next((name for name in ('stat-num', 'stat-lbl', 'group-title', 'meta') if name in classes), '')
        if tag == 'title':
            capture = 'title'
        self.stack.append((tag, capture, [] if capture else None))

    def handle_data(self, data):
        for _, _, buffer in self.stack:
            if buffer is not None:
                buffer.append(data)

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack)-1, -1, -1) if self.stack[i][0] == tag), None)
        if index is None:
            return
        frames = self.stack[index:]
        del self.stack[index:]
        for _, capture, buffer in frames:
            if buffer is None:
                continue
            text = ''.join(buffer).strip()
            if capture == 'stat-num':
                self.number = int(text) if text.isdigit() else None
            elif capture == 'stat-lbl' and self.number is not None:
                self.stats[text] = self.number
            elif capture == 'group-title' and text not in self.groups:
                self.groups.append(text)
            elif capture == 'meta':
                match = re.search(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}', text)
                if match:
                    self.created = _date(match[0])
            elif capture == 'title':
                self.title = text


@lru_cache(maxsize=256)
def _report_cached(path, mtime, size):
    del mtime, size  # File identity is part of the cache key.
    text = Path(path).read_text(encoding='utf-8')
    parser = _ReportSummary()
    parser.feed(text)
    if parser.title != 'App QA Report' or '</html>' not in text.lower():
        return None
    if not {'전체', '통과', '실패'} <= parser.stats.keys():
        return None
    match = _REPORT_NAME.fullmatch(Path(path).name)
    if not match:
        return None
    started = _date(datetime.strptime(match[2], '%Y%m%d_%H%M%S').replace(microsecond=int(match[3] or '0')*1000).isoformat())
    executed = parser.created or started
    counts = {'total': parser.stats['전체'], 'passed': parser.stats['통과'], 'failed': parser.stats['실패'], 'skipped': parser.stats.get('건너뜀', 0)}
    if counts['total'] != counts['passed'] + counts['failed'] + counts['skipped']:
        return None
    ids = {parser.run_id} if parser.run_id else {item.group(0) for item in _RUN_ID.finditer(text)}
    platforms = {item.split('_')[1] for item in ids}
    platform = match[1] or (next(iter(platforms)) if len(platforms) == 1 else 'unknown')
    return {**counts, 'id': 'report:'+Path(path).name, 'type': 'execution', 'platform': platform,
            'executedAt': executed.isoformat(), 'duration': None, 'groups': parser.groups,
            'reportName': Path(path).name, '_started': started,
            'runId': next(iter(ids)) if len(ids) == 1 else None}


@lru_cache(maxsize=512)
def _json_cached(path, mtime, size):
    del mtime, size
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _cached(path, loader):
    try:
        stat = path.stat()
        return loader(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, TypeError):
        return None


def _manifest_summary(data, run_id):
    finished = _date(data.get('finished_at'))
    started = _date(data.get('started_at'))
    if started is None:
        return None
    entries = data.get('entries', [])
    attempts = [entry.get('attempts') or [entry] for entry in entries]
    latest = [items[-1].get('outcome') for items in attempts]
    groups = []
    for entry in entries:
        match = re.match(r'tests/generated/(?:android|ios)/([^/]+)/', str(entry.get('nodeid', '')))
        if match and match[1] not in groups:
            groups.append(match[1])
    kind = data.get('type')
    complete = finished is not None and bool(latest) and all(outcome in {'passed', 'failed', 'error', 'skipped'} for outcome in latest)
    status = ('failed' if any(outcome in {'failed', 'error'} for outcome in latest) else 'passed') if complete else 'incomplete'
    return {'id': run_id, 'runId': run_id, 'type': kind if kind in {'quick', 'pipeline'} else 'execution',
            'platform': data.get('platform', run_id.split('_')[1]), 'executedAt': (finished or started).isoformat(),
            'duration': max(0, (finished-started).total_seconds()) if finished else None, 'total': len(latest),
            'passed': latest.count('passed'), 'failed': latest.count('failed')+latest.count('error'),
            'skipped': latest.count('skipped'), 'groups': groups, 'reportName': None,
            'status': status, 'countsComplete': complete,
            'firstPass': complete and bool(attempts) and all(items[0].get('outcome') == 'passed' for items in attempts),
            '_started': started}


def execution_summary(data, run_id, fallback_time):
    """Normalize owned result metadata for history and artifact-list consumers."""
    if not isinstance(data, dict) or data.get('run_id') != run_id:
        return None
    status = data.get('status')
    if status not in {'running', 'passed', 'failed', 'cancelled', 'interrupted', 'timed_out'}:
        return None
    result = data.get('execute_results') or {}
    summary = result.get('summary') or {} if isinstance(result, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    counts = {name: value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
              for name in ('total', 'passed', 'failed', 'skipped') for value in [summary.get(name, 0)]}
    # Older JSON summaries omit skipped; retain the known total without inventing outcomes.
    complete = (status in {'passed', 'failed'} and counts['total'] > 0
                and counts['passed'] + counts['failed'] + counts['skipped'] == counts['total'])
    started = _date(data.get('started_at'))
    finished = _date(data.get('finished_at'))
    timestamp = finished or _date(data.get('updated_at')) or started or fallback_time
    groups = []
    for value in (result.get('passed', []) + [item.get('file', '') for item in result.get('errors', []) if isinstance(item, dict)]) if isinstance(result, dict) else []:
        match = re.match(r'tests/generated/(?:android|ios)/([^/]+)/', str(value))
        if match and match[1] not in groups:
            groups.append(match[1])
    return {**counts, 'id': run_id, 'runId': run_id, 'status': status,
            'platform': data.get('platform') or run_id.split('_')[1],
            'type': data.get('run_type', 'execution'), 'executedAt': timestamp.isoformat(),
            'duration': max(0, (finished-started).total_seconds()) if finished and started else None,
            'groups': groups, 'reportName': None, 'countsComplete': complete,
            'error': str(data.get('error') or ''),
            'recoveredAfterRestart': data.get('recovered_after_restart') is True,
            'workflowStatus': data.get('workflow_status'),
            'workflowError': str(data.get('workflow_error') or ''),
            '_started': started or fallback_time}


def _entries(root, reports_dir):
    manifests = {}
    for path in (root/'state/runs').glob('*/artifacts/manifest.json'):
        if path.is_symlink() or not _RUN_ID.fullmatch(path.parent.parent.name):
            continue
        data = _cached(path, _json_cached)
        if not isinstance(data, dict):
            continue
        rid = path.parent.parent.name
        try:
            summary = _manifest_summary(data, rid)
        except (KeyError, TypeError, AttributeError):
            continue
        if summary:
            manifests[rid] = summary
    combined = dict(manifests)
    for path in sorted(reports_dir.glob('report_*.html')):
        if path.is_symlink():
            continue
        raw = _cached(path, _report_cached)
        if raw is None:
            continue
        entry = dict(raw)
        rid = entry.get('runId')
        if not rid:
            end = _date(entry['executedAt'])
            matches = [key for key, value in manifests.items()
                       if value['platform'] == entry['platform'] and set(value['groups']) == set(entry['groups'])
                       and entry['_started']-timedelta(seconds=3) <= value['_started'] <= end
                       and all(value[name] == entry[name] for name in ('total', 'passed', 'failed', 'skipped'))]
            if len(matches) == 1:
                rid = matches[0]
        if rid in manifests:
            current = combined[rid]
            # A retry may write multiple reports for one logical run. Keep its last report.
            if not current['reportName'] or entry['reportName'] > current['reportName']:
                current = dict(manifests[rid])
                current['reportName'] = entry['reportName']
                combined[rid] = current
        else:
            if rid:
                entry['id'] = rid
                entry['runId'] = rid
            combined[entry['id']] = entry
    for path in (root/'state/runs').glob('*/execution_result.json'):
        rid = path.parent.name
        if path.is_symlink() or not _RUN_ID.fullmatch(rid):
            continue
        data = _cached(path, _json_cached)
        previous = combined.get(rid, {})
        try:
            fallback = _date(previous.get('executedAt')) or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            entry = execution_summary(data, rid, fallback)
        except (OSError, TypeError, AttributeError):
            continue
        if entry is None:
            continue
        if entry['duration'] is None and not data.get('started_at') and not data.get('finished_at'):
            entry['duration'] = previous.get('duration')
        entry['groups'] = entry['groups'] or previous.get('groups', [])
        entry['type'] = data.get('run_type') or previous.get('type', 'execution')
        entry['reportName'] = previous.get('reportName')
        if data.get('report_path'):
            report = Path(data['report_path'])
            if report.name == data['report_path'] or report.resolve().parent == reports_dir.resolve():
                if (reports_dir/report.name).is_file():
                    entry['reportName'] = report.name
        if not entry['countsComplete']:
            entry['firstPass'] = False
        elif 'firstPass' in previous:
            entry['firstPass'] = previous['firstPass']
        combined[rid] = entry
    for value in combined.values():
        value.pop('_started', None)
        value.setdefault('status', 'failed' if value['failed'] else 'passed')
        value.setdefault('countsComplete', True)
        value['rate'] = round(value['passed']/value['total']*100) if value['countsComplete'] and value['total'] else None
    return sorted(combined.values(), key=lambda item: (item['executedAt'], item['id']), reverse=True)


def load_run_history(root: Path, reports_dir: Path, limit=50):
    with _LOCK:
        entries = _entries(root, reports_dir)
        marker = _cached(root/'state/run_history_reset.json', _json_cached) or {}
        if not isinstance(marker, dict):
            marker = {}
        cutoff = _date(marker.get('cutoff'))
        hidden = set(marker.get('ids', []))
        return [entry for entry in entries if entry['id'] not in hidden and
                (cutoff is None or _date(entry['executedAt']) > cutoff)][:limit]


def reset_run_history(root: Path, reports_dir: Path):
    with _LOCK:
        entries = _entries(root, reports_dir)
        path = root/'state/run_history_reset.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'cutoff': _now().isoformat(), 'ids': [entry['id'] for entry in entries]}), encoding='utf-8')
        temporary.replace(path)
