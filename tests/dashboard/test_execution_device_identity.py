"""Picker identities use mocked discovery and a temporary device registry."""
import json
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agents.dashboard.routes import pipeline


def test_android_picker_matches_each_avd_and_rejects_missing_real_identity(monkeypatch, tmp_path):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/devices.json').write_text(json.dumps({'android': {
        'emulator': [{'avd': 'Stopped', 'deviceName': 'Stopped'}, {'avd': 'Running', 'deviceName': 'Running'}],
        'real_device': [{'udid': '', 'deviceName': 'Unspecified'}, {'udid': 'usb-real', 'deviceName': 'Phone'}, {'udid': 'emulator-5554', 'deviceName': 'Wrong kind'}],
    }}))
    monkeypatch.setattr(pipeline, 'PROJECT_ROOT', tmp_path)
    def run(command, **_):
        if command[-1] == 'devices':
            return SimpleNamespace(stdout='List of devices attached\nemulator-5554\tdevice\nusb-real\tdevice\n', returncode=0)
        if 'emu' in command:
            return SimpleNamespace(stdout='Running\nOK\n', returncode=0)
        return SimpleNamespace(stdout='', returncode=1)
    monkeypatch.setattr(pipeline.subprocess, 'run', run)
    app = FastAPI()
    app.include_router(pipeline.router)
    rows = TestClient(app).get('/api/devices?platform=android').json()['devices']
    assert rows[0]['connected'] is False and rows[0]['udid'] == ''
    assert rows[1]['connected'] is True and rows[1]['udid'] == 'emulator-5554'
    assert rows[2]['connected'] is False and rows[2]['udid'] == ''
    assert rows[3]['connected'] is True and rows[3]['udid'] == 'usb-real'
    assert rows[4]['connected'] is False


def test_ios_real_picker_requires_connected_physical_hardware_udid(monkeypatch, tmp_path):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/devices.json').write_text(json.dumps({'ios': {'real_device': [
        {'udid':'hardware-live','deviceName':'Phone'}, {'udid':'core-device-id','deviceName':'Wrong ID'},
        {'udid':'hardware-off','deviceName':'Offline'}, {'udid':'sim-id','deviceName':'Wrong kind'},
    ]}}))
    monkeypatch.setattr(pipeline, 'PROJECT_ROOT', tmp_path)
    def run(command, **_):
        if 'simctl' in command:
            return SimpleNamespace(stdout=json.dumps({'devices':{}}), returncode=0)
        return SimpleNamespace(stdout=json.dumps({'result':{'devices':[
            {'identifier':'core-device-id','hardwareProperties':{'udid':'hardware-live','reality':'physical'},'connectionProperties':{'tunnelState':'connected'}},
            {'hardwareProperties':{'udid':'hardware-off','reality':'physical'},'connectionProperties':{'tunnelState':'disconnected'}},
            {'hardwareProperties':{'udid':'sim-id','reality':'virtual'},'connectionProperties':{'tunnelState':'connected'}},
        ]}}), returncode=0)
    monkeypatch.setattr(pipeline.subprocess, 'run', run)
    app = FastAPI()
    app.include_router(pipeline.router)
    rows = TestClient(app).get('/api/devices?platform=ios').json()['devices']
    assert [row['connected'] for row in rows] == [True, False, False, False]
