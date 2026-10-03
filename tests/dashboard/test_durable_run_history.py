"""Server history backfills saved executions; reset only writes temp cutoff state."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agents.dashboard.routes import api


def report(root, name, *, created='2026-10-02 12:00:10', passed=1, failed=0, skipped=0, run_id=''):
    directory=root/'tests/reports';directory.mkdir(parents=True,exist_ok=True)
    text='<!doctype html><html><head><title>App QA Report</title></head><body>'
    text+=f'<div class="meta">{created} · 1개 그룹 · {passed+failed+skipped}건</div>'
    for label,count in [('전체',passed+failed+skipped),('통과',passed),('실패',failed),('건너뜀',skipped)]:
        text+=f'<div class="stat-card"><div class="stat-num">{count}</div><div class="stat-lbl">{label}</div></div>'
    text+='<span class="group-title">settings</span>'
    if run_id:text+=f'<a href="/api/run_artifacts/{run_id}/video?nodeid=x">영상</a>'
    text+='</body></html>'
    (directory/name).write_text(text)


def manifest(root, run_id, *, finished='2026-10-02T12:00:09+09:00', outcomes=('passed',), started='2026-10-02T12:00:01+09:00'):
    directory=root/'state/runs'/run_id/'artifacts';directory.mkdir(parents=True,exist_ok=True)
    data={'run_id':run_id,'platform':'android','started_at':started,'finished_at':finished,
          'entries':[{'nodeid':f'tests/generated/android/settings/test{i}.py::test',
                      'attempts':[{'n':1,'outcome':outcome}]} for i,outcome in enumerate(outcomes)]}
    (directory/'manifest.json').write_text(json.dumps(data))


@pytest.fixture
def history_client(monkeypatch,tmp_path):
    monkeypatch.setattr(api,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(api,'REPORTS_DIR',tmp_path/'tests/reports')
    app=FastAPI();app.include_router(api.router)
    return TestClient(app)


def test_existing_report_backfills_without_browser_storage(history_client,tmp_path):
    report(tmp_path,'report_android_20261002_120000_001.html',passed=2,failed=1,skipped=1)
    response=history_client.get('/api/run-history')
    assert response.status_code==200
    entry=response.json()['entries'][0]
    assert (entry['total'],entry['passed'],entry['failed'],entry['skipped'])==(4,2,1,1)
    assert entry['platform']=='android' and entry['type']=='execution'
    assert entry['groups']==['settings']
    assert datetime.fromisoformat(entry['executedAt']).tzinfo is not None
    assert entry['reportName']=='report_android_20261002_120000_001.html'
    assert 'healCount' not in entry


def test_completed_manifest_and_retry_reports_form_one_execution(history_client,tmp_path):
    rid='run_android_20261002_120000_000'
    manifest(tmp_path,rid,outcomes=('passed','failed','skipped'))
    report(tmp_path,'report_android_20261002_120000_001.html',run_id=rid,passed=0,failed=2)
    report(tmp_path,'report_android_20261002_120005_002.html',run_id=rid,passed=1,failed=1,skipped=1)
    entries=history_client.get('/api/run-history').json()['entries']
    assert len(entries)==1
    assert entries[0]['runId']==rid
    assert (entries[0]['passed'],entries[0]['failed'],entries[0]['skipped'])==(1,1,1)
    assert entries[0]['duration']==8
    assert entries[0]['reportName']=='report_android_20261002_120005_002.html'


def test_all_pass_report_without_artifact_links_matches_only_unique_manifest(history_client,tmp_path):
    rid='run_android_20261002_120000_000'
    manifest(tmp_path,rid)
    report(tmp_path,'report_android_20261002_120000_001.html')
    entries=history_client.get('/api/run-history').json()['entries']
    assert len(entries)==1 and entries[0]['runId']==rid
    assert entries[0]['firstPass'] is True


def test_all_pass_report_start_can_follow_manifest_by_milliseconds(history_client,tmp_path):
    rid='run_android_20261002_120000_289'
    manifest(tmp_path,rid,started='2026-10-02T12:00:00.100+09:00')
    report(tmp_path,'report_android_20261002_120000_376.html')
    entries=history_client.get('/api/run-history').json()['entries']
    assert len(entries)==1 and entries[0]['runId']==rid


def test_delayed_successful_retry_report_keeps_explicit_execution_identity(history_client,tmp_path):
    from scripts.report_html import build_report
    rid='run_android_20261002_120000_000'
    manifest(tmp_path,rid,finished='2026-10-02T12:01:09+09:00')
    report(tmp_path,'report_android_20261002_120000_001.html',run_id=rid,passed=0,failed=1)
    name='report_android_20261002_120100_001.html'
    document=build_report([{'label':'settings','rows_html':'','pass_cnt':1,'total_cnt':1,
                           'all_pass':True,'has_tests':True}],
                          {'passed':1,'failed':0},'2026-10-02 12:01:10',
                          platform='android',run_id=rid)
    assert f'<meta name="qa-run-id" content="{rid}">' in document
    assert 'href="/api/run_artifacts/' not in document
    document=document.replace('</body>','<pre>previous run_android_20261001_120000_000</pre></body>')
    (tmp_path/'tests/reports'/name).write_text(document)
    entries=history_client.get('/api/run-history').json()['entries']
    assert len(entries)==1
    assert entries[0]['runId']==rid and entries[0]['reportName']==name


def test_report_without_links_is_not_matched_to_different_counts(history_client,tmp_path):
    manifest(tmp_path,'run_android_20261002_120000_289',outcomes=('passed','failed'))
    report(tmp_path,'report_android_20261002_120000_376.html')
    assert len(history_client.get('/api/run-history').json()['entries'])==2


def test_report_remains_history_after_artifact_removal_and_cache_updates(history_client,tmp_path):
    rid='run_android_20261002_120000_289'
    name='report_android_20261002_120000_376.html'
    report(tmp_path,name,run_id=rid)
    entry=history_client.get('/api/run-history').json()['entries'][0]
    assert entry['runId']==rid and entry['passed']==1 and entry['duration'] is None
    report(tmp_path,name,run_id=rid,passed=0,failed=1)
    assert history_client.get('/api/run-history').json()['entries'][0]['failed']==1


def test_legacy_filename_uses_linked_platform_without_inventing_it(history_client,tmp_path):
    report(tmp_path,'report_20261002_120000.html',run_id='run_ios_20261002_120000_289')
    report(tmp_path,'report_20261002_120100.html',created='2026-10-02 12:01:10')
    entries=history_client.get('/api/run-history').json()['entries']
    assert len(entries)==2
    assert entries[0]['platform']=='unknown'
    assert entries[1]['platform']=='ios'


def test_unfinished_manifest_is_visible_without_claiming_report_success(history_client,tmp_path):
    rid='run_android_20261002_120000_000'
    manifest(tmp_path,rid,finished=None)
    report(tmp_path,'report_android_20261002_120000_001.html',run_id=rid)
    entries = history_client.get('/api/run-history').json()['entries']
    assert len(entries) == 1
    assert entries[0]['status'] == 'incomplete'
    assert entries[0]['rate'] is None
    assert entries[0]['countsComplete'] is False


def test_reset_is_persistent_and_does_not_delete_report_or_artifact(history_client,tmp_path,monkeypatch):
    from utils import run_history
    monkeypatch.setattr(run_history,'_now',lambda:datetime(2026,10,2,3,1,tzinfo=timezone.utc))
    rid='run_android_20261002_120000_000';manifest(tmp_path,rid)
    name='report_android_20261002_120000_001.html';report(tmp_path,name,run_id=rid)
    assert history_client.get('/api/run-history').json()['entries']
    assert history_client.delete('/api/run-history').json()['ok'] is True
    assert history_client.get('/api/run-history').json()['entries']==[]
    assert (tmp_path/'tests/reports'/name).exists()
    assert (tmp_path/'state/runs'/rid/'artifacts/manifest.json').exists()
    (tmp_path/'tests/reports'/name).touch()
    assert history_client.get('/api/run-history').json()['entries']==[]
    assert (tmp_path/'state/run_history_reset.json').exists()
    report(tmp_path,'report_android_20261002_120200_000.html',created='2026-10-02 12:02:10')
    assert len(history_client.get('/api/run-history').json()['entries'])==1


def test_bad_files_are_ignored_and_latest_fifty_are_returned(history_client,tmp_path):
    directory=tmp_path/'tests/reports';directory.mkdir(parents=True)
    (directory/'report_android_bad.html').write_text('unfinished report')
    for number in range(55):
        report(tmp_path,f'report_android_20261002_1200{number:02}_000.html',created=f'2026-10-02 12:00:{number:02}')
    entries=history_client.get('/api/run-history').json()['entries']
    assert len(entries)==50
    assert entries[0]['executedAt']>entries[-1]['executedAt']


def execution_result(root, rid, **overrides):
    directory = root / 'state/runs' / rid
    directory.mkdir(parents=True, exist_ok=True)
    data = {'run_id': rid, 'platform': 'android', 'status': 'failed',
            'started_at': '2026-10-02T03:00:00+00:00',
            'finished_at': '2026-10-02T03:00:09+00:00',
            'execute_results': {'passed': [], 'errors': [],
                                'summary': {'total': 0, 'passed': 0, 'failed': 0}}}
    data.update(overrides)
    (directory / 'execution_result.json').write_text(json.dumps(data))


@pytest.mark.parametrize('status', ['failed', 'cancelled', 'interrupted', 'timed_out'])
def test_result_without_manifest_or_report_is_visible(history_client, tmp_path, status):
    rid = 'run_android_20261002_120000_000'
    execution_result(tmp_path, rid, status=status, error='Appium disconnected', recovered_after_restart=True)
    entries = history_client.get('/api/run-history').json()['entries']
    assert len(entries) == 1
    assert entries[0]['runId'] == rid
    assert entries[0]['status'] == status
    assert entries[0]['error'] == 'Appium disconnected'
    assert entries[0]['recoveredAfterRestart'] is True
    assert entries[0]['total'] == 0
    assert entries[0]['rate'] is None


def test_terminal_result_overrides_unfinished_manifest_and_old_success_report(history_client, tmp_path):
    rid = 'run_android_20261002_120000_000'
    manifest(tmp_path, rid, finished=None, outcomes=('passed',))
    report(tmp_path, 'report_android_20261002_120000_001.html', run_id=rid)
    execution_result(tmp_path, rid, status='timed_out', error='deadline exceeded')
    entries = history_client.get('/api/run-history').json()['entries']
    assert len(entries) == 1
    entry = entries[0]
    assert entry['status'] == 'timed_out'
    assert entry['passed'] == 0
    assert entry['rate'] is None
    assert entry['firstPass'] is False
    assert entry['countsComplete'] is False
    assert entry['groups'] == ['settings']
    assert entry['reportName'] == 'report_android_20261002_120000_001.html'


def test_running_result_does_not_publish_previous_attempt_as_success(history_client, tmp_path):
    rid = 'run_android_20261002_120000_000'
    manifest(tmp_path, rid)
    execution_result(tmp_path, rid, status='running', finished_at=None, recovered_after_restart=True,
                     execute_results={'passed': ['tc.py::test_ok'], 'errors': [],
                                      'summary': {'total': 1, 'passed': 1, 'failed': 0}})
    entry = history_client.get('/api/run-history').json()['entries'][0]
    assert entry['status'] == 'running'
    assert entry['countsComplete'] is False
    assert entry['rate'] is None
    assert entry['recoveredAfterRestart'] is True


def test_mismatched_result_run_id_is_ignored(history_client, tmp_path):
    execution_result(tmp_path, 'run_android_20261002_120000_000', run_id='run_ios_20261002_120000_000')
    assert history_client.get('/api/run-history').json()['entries'] == []


@pytest.mark.parametrize('with_manifest', [False, True])
def test_legacy_result_rewrite_preserves_known_execution_time(history_client, tmp_path, with_manifest):
    import os
    rid = 'run_android_20261002_120000_000'
    if with_manifest:
        manifest(tmp_path, rid)
    report(tmp_path, 'report_android_20261002_120000_001.html', run_id=rid)
    previous = history_client.get('/api/run-history').json()['entries'][0]
    execution_result(tmp_path, rid, status='passed', started_at=None, finished_at=None,
                     recovered_after_restart=True,
                     execute_results={'passed': ['tc.py::test_ok'], 'errors': [],
                                      'summary': {'total': 1, 'passed': 1, 'failed': 0}})
    path = tmp_path / 'state/runs' / rid / 'execution_result.json'
    os.utime(path, (1900000000, 1900000000))
    restored = history_client.get('/api/run-history').json()['entries'][0]
    assert restored['executedAt'] == previous['executedAt']
    assert restored['duration'] == previous['duration']
    assert restored['recoveredAfterRestart'] is True


def test_finished_manifest_without_test_outcomes_is_not_success(history_client, tmp_path):
    rid = 'run_android_20261002_120000_000'
    manifest(tmp_path, rid, outcomes=())
    entry = history_client.get('/api/run-history').json()['entries'][0]
    assert entry['status'] == 'incomplete'
    assert entry['countsComplete'] is False
    assert entry['rate'] is None


def test_unaccounted_terminal_counts_are_not_complete(history_client, tmp_path):
    rid = 'run_android_20261002_120000_000'
    execution_result(tmp_path, rid, status='passed', execute_results={
        'passed': ['tc.py::test_ok'], 'errors': [],
        'summary': {'total': 5, 'passed': 2, 'failed': 0}})
    entry = history_client.get('/api/run-history').json()['entries'][0]
    assert entry['countsComplete'] is False
    assert entry['rate'] is None
    assert entry['skipped'] == 0


def test_completed_folder_retains_pass_and_exposes_interrupted_remaining_work(history_client, tmp_path):
    rid = 'run_android_20261002_120000_000'
    execution_result(tmp_path, rid, status='passed', recovered_after_restart=True,
                     workflow_status='interrupted', workflow_error='남은 단계는 자동 실행하지 않습니다',
                     execute_results={'passed': ['tc.py::test_ok'], 'errors': [],
                                      'summary': {'total': 1, 'passed': 1, 'failed': 0}})
    entry = history_client.get('/api/run-history').json()['entries'][0]
    assert entry['status'] == 'passed'
    assert entry['passed'] == 1 and entry['rate'] == 100
    assert entry['workflowStatus'] == 'interrupted'
    assert entry['workflowError'] == '남은 단계는 자동 실행하지 않습니다'


@pytest.mark.parametrize('kind', ['quick', 'pipeline'])
@pytest.mark.parametrize('with_manifest', [False, True])
def test_report_type_survives_unknown_result_and_manifest(history_client, tmp_path, kind, with_manifest):
    from scripts.report_html import build_report
    rid = 'run_android_20261002_120000_000'
    directory = tmp_path / 'tests/reports'
    directory.mkdir(parents=True)
    document = build_report([], {'passed': 1}, '2026-10-02 12:00:10',
                            platform='android', run_id=rid, run_type=kind)
    assert f'<meta name="qa-run-type" content="{kind}">' in document
    (directory / 'report_android_20261002_120000_001.html').write_text(document)
    if with_manifest:
        manifest(tmp_path, rid)
    assert history_client.get('/api/run-history').json()['entries'][0]['type'] == kind
    execution_result(tmp_path, rid, run_type='execution')
    assert history_client.get('/api/run-history').json()['entries'][0]['type'] == kind


@pytest.mark.parametrize('kind', [None, 'invalid', {}, 'execution'])
def test_report_type_is_validated_and_legacy_remains_unknown(history_client, tmp_path, kind):
    from scripts.report_html import build_report
    directory = tmp_path / 'tests/reports'
    directory.mkdir(parents=True)
    document = build_report([], {'passed': 1}, '2026-10-02 12:00:10', run_type=kind)
    assert '<meta name="qa-run-type" content="execution">' in document
    (directory / 'report_android_20261002_120000_001.html').write_text(document)
    assert history_client.get('/api/run-history').json()['entries'][0]['type'] == 'execution'


def test_unknown_result_preserves_known_manifest_type(history_client, tmp_path):
    rid = 'run_android_20261002_120000_000'
    manifest(tmp_path, rid)
    path = tmp_path / 'state/runs' / rid / 'artifacts/manifest.json'
    data = json.loads(path.read_text())
    data['type'] = 'pipeline'
    path.write_text(json.dumps(data))
    execution_result(tmp_path, rid, run_type='execution')
    assert history_client.get('/api/run-history').json()['entries'][0]['type'] == 'pipeline'
