"""Healing must preserve the selected run and roll back failed candidates."""
import importlib.util
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[2]


@pytest.fixture(autouse=True)
def restore_signal_handler(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    original = signal.getsignal(signal.SIGTERM)
    yield
    signal.signal(signal.SIGTERM, original)


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('outcome', ['failure', 'exception', 'success'])
def test_heal_preserves_pre_attempt_files(tmp_path, monkeypatch, outcome):
    heal = load_script('06_heal')
    config = tmp_path / 'config'
    config.mkdir()
    registry = config / 'locators.json'
    original_registry = b'{"targets": {"login.button": {"android": {"strategy": "ID", "value": "login", "surface": "native"}}}}\n'
    registry.write_bytes(original_registry)
    source = b'SEL_BUTTON = "login"  # target_ref: login.button\r\n'
    test_file = tmp_path / 'tc_001_login.py'
    test_file.write_bytes(source)
    test_file.with_suffix('.py.backup').write_text('stale backup')
    monkeypatch.setattr(heal, 'CONFIG_DIR', config)
    monkeypatch.setattr(heal, 'load_registry', lambda: json.loads(registry.read_text()))
    monkeypatch.setattr(heal, 'save_registry', lambda value: registry.write_text(json.dumps(value)))

    def verify(_):
        if outcome == 'exception':
            raise RuntimeError('device disconnected')
        return outcome == 'success'

    monkeypatch.setattr(heal, '_run_pytest_single', verify)
    snapshot = {'login': {'android': {'xml': '<root><node resource-id="app:id/login"/></root>'}}}
    if outcome == 'exception':
        with pytest.raises(RuntimeError, match='disconnected'):
            heal.heal_file_xml(str(test_file), snapshot)
    else:
        result = heal.heal_file_xml(str(test_file), snapshot)
        assert ('strategy' in result) == (outcome == 'success')
    if outcome != 'success':
        assert test_file.read_bytes() == source
        assert registry.read_bytes() == original_registry
    else:
        assert 'app:id/login' in test_file.read_text()
        assert json.loads(registry.read_text())['targets']['login.button']['android']['value'] == 'app:id/login'


def test_heal_snapshot_and_pytest_inherit_selected_context(tmp_path, monkeypatch):
    heal = load_script('06_heal')
    monkeypatch.setenv('DEVICE_MODE', 'real_device')
    monkeypatch.setenv('DEVICE_UDID', 'selected-device')
    monkeypatch.setenv('QA_RUN_ID', 'run-selected')
    seen = []
    monkeypatch.setattr(heal.subprocess, 'run', lambda cmd, **kwargs: seen.append((cmd, kwargs)) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(heal, 'load_state', lambda: {'dom_info': {}})
    heal._refresh_inspector_snapshot('ios')
    heal._run_pytest_single(str(tmp_path / 'test_example.py'))
    analyzer_cmd = seen[0][0]
    assert analyzer_cmd[analyzer_cmd.index('--mode') + 1] == 'real_device'
    assert analyzer_cmd[analyzer_cmd.index('--udid') + 1] == 'selected-device'
    for _, kwargs in seen:
        env = kwargs.get('env') or os.environ
        assert env['QA_RUN_ID'] == 'run-selected'
        assert env['DEVICE_UDID'] == 'selected-device'


@pytest.mark.parametrize('platform,env_mode,expected', [('ios', '', 'simulator'), ('android', '', 'emulator'), ('ios', 'real_device', 'real_device')])
def test_analyzer_accepts_exact_device_and_platform_mode(tmp_path, monkeypatch, platform, env_mode, expected):
    analyze = load_script('01_analyze')
    for filename in ('screens.json', 'test_data.json'):
        (tmp_path / filename).write_text('{}')
    monkeypatch.setattr(analyze, 'CONFIG_DIR', tmp_path)
    monkeypatch.setattr(analyze, 'load_state', lambda: {})
    monkeypatch.setattr(analyze, 'save_state', lambda state: None)
    monkeypatch.setenv('DEVICE_MODE', env_mode)
    monkeypatch.setenv('DEVICE_UDID', 'inherited-device')
    monkeypatch.setattr('sys.argv', ['01_analyze.py', '--platform', platform, '--udid', 'selected-device'])
    driver_module = __import__(f'drivers.{platform}_driver', fromlist=['create_driver'])
    seen = []
    monkeypatch.setattr(driver_module, 'create_driver', lambda **kwargs: seen.append(kwargs) or SimpleNamespace(quit=lambda: None))
    analyze.main()
    assert seen == [{'mode': expected, 'udid': 'selected-device'}]


@pytest.mark.parametrize('outcome', ['failure', 'exception'])
def test_fallback_restores_current_source_not_old_backup(tmp_path, monkeypatch, outcome):
    heal = load_script('06_heal')
    monkeypatch.setattr(heal, 'CONFIG_DIR', tmp_path)
    source = b'SEL_BUTTON = "login"\r\nelement = driver.find_element(AppiumBy.ACCESSIBILITY_ID, SEL_BUTTON)\r\n'
    path = tmp_path / 'tc_001_login.py'
    path.write_bytes(source)
    path.with_suffix('.py.backup').write_text('stale backup')
    def verify(_):
        if outcome == 'exception':
            raise RuntimeError('session gone')
        return False
    monkeypatch.setattr(heal, '_run_pytest_single', verify)
    if outcome == 'exception':
        with pytest.raises(RuntimeError, match='session gone'):
            heal.heal_file_fallback(str(path))
    else:
        assert 'strategy' not in heal.heal_file_fallback(str(path))
    assert path.read_bytes() == source
    assert not (tmp_path / 'locators.json').exists()


def test_registry_commit_error_restores_both_files(tmp_path, monkeypatch):
    heal = load_script('06_heal')
    monkeypatch.setattr(heal, 'CONFIG_DIR', tmp_path)
    path = tmp_path / 'tc_001_login.py'
    source = b'SEL_BUTTON = "login"  # target_ref: login.button\n'
    path.write_bytes(source)
    registry_path = tmp_path / 'locators.json'
    original = b'{ "targets": {} }\n'
    registry_path.write_bytes(original)
    monkeypatch.setattr(heal, 'load_registry', lambda: json.loads(registry_path.read_bytes()))
    def broken_save(registry):
        registry_path.write_bytes(b'partial write')
        raise OSError('disk error')
    monkeypatch.setattr(heal, 'save_registry', broken_save)
    monkeypatch.setattr(heal, '_run_pytest_single', lambda _: True)
    with pytest.raises(OSError, match='disk error'):
        heal.heal_file_xml(str(path), {'login': {'xml': '<node resource-id="app:id/login"/>'}})
    assert path.read_bytes() == source
    assert registry_path.read_bytes() == original


@pytest.mark.parametrize('scoped_result', [None, {'run_id': 'owned', 'status': 'error', 'exit_code': 2, 'execute_results': {'errors': []}}])
def test_heal_missing_run_failure_never_uses_global_errors(tmp_path, monkeypatch, scoped_result):
    heal = load_script('06_heal')
    from scripts.run_results import write_execution_result
    if scoped_result is not None:
        write_execution_result(tmp_path, 'owned', scoped_result)
    monkeypatch.setattr(heal, 'ROOT', tmp_path)
    monkeypatch.setenv('QA_RUN_ID', 'owned')
    monkeypatch.setattr('sys.argv', ['06_heal.py'])
    monkeypatch.setattr(heal, 'load_state', lambda: {'execute_results': {'errors': [{'file': 'stale.py'}]}})
    monkeypatch.setattr(heal, '_extract_failed_files', lambda _: pytest.fail('must not use global errors'))
    monkeypatch.setattr(heal, 'save_state', lambda _: None)
    with pytest.raises(SystemExit) as failure:
        heal.main()
    assert failure.value.code == 1


def test_heal_uses_owned_errors_and_retains_fresh_snapshot(tmp_path, monkeypatch):
    heal = load_script('06_heal')
    from scripts.run_results import write_execution_result
    path = tmp_path / 'tc_001_login.py'
    path.write_text('irrelevant')
    write_execution_result(tmp_path, 'owned', {'status': 'failed', 'exit_code': 1, 'execute_results': {'errors': [{'file': str(path)}]}})
    monkeypatch.setattr(heal, 'ROOT', tmp_path)
    monkeypatch.setenv('QA_RUN_ID', 'owned')
    monkeypatch.setattr('sys.argv', ['06_heal.py'])
    monkeypatch.setattr(heal, 'load_state', lambda: {'execute_results': {'errors': [{'file': 'stale.py'}]}, 'dom_info': {'old': {}}})
    fresh = {'login': {'android': {'xml': '<root/>'}}}
    monkeypatch.setattr(heal, '_refresh_inspector_snapshot', lambda _: fresh)
    called = []
    monkeypatch.setattr(heal, 'heal_file_xml', lambda file, snapshot, platform: called.append((file, snapshot)) or {'strategy': 'ID'})
    monkeypatch.setattr(heal, '_append_lessons_learned', lambda *args: None)
    saved = []
    monkeypatch.setattr(heal, 'save_state', saved.append)
    heal.main()
    assert called == [(str(path), fresh)]
    assert saved[-1]['dom_info'] == fresh


def test_sigterm_during_heal_validation_rolls_back(tmp_path, monkeypatch):
    import signal
    heal = load_script('06_heal')
    from scripts.run_results import write_execution_result
    monkeypatch.setattr(heal, 'ROOT', tmp_path)
    monkeypatch.setattr(heal, 'CONFIG_DIR', tmp_path)
    monkeypatch.setenv('QA_RUN_ID', 'cancelled')
    monkeypatch.setattr('sys.argv', ['06_heal.py'])
    path = tmp_path / 'tc_001_login.py'
    original = b'SEL_BUTTON = "login"  # target_ref: login.button\n'
    path.write_bytes(original)
    registry = tmp_path / 'locators.json'
    registry_before = b'{"targets": {}}\n'
    registry.write_bytes(registry_before)
    write_execution_result(tmp_path, 'cancelled', {'exit_code': 1, 'execute_results': {'errors': [{'file': str(path)}]}})
    monkeypatch.setattr(heal, 'load_state', lambda: {})
    monkeypatch.setattr(heal, 'load_registry', lambda: json.loads(registry.read_bytes()))
    monkeypatch.setattr(heal, 'save_registry', lambda data: registry.write_text(json.dumps(data)))
    monkeypatch.setattr(heal, '_refresh_inspector_snapshot', lambda _: {'login': {'xml': '<node resource-id="app:id/login"/>'}})
    handlers = {}
    monkeypatch.setattr(signal, 'signal', lambda number, handler: handlers.__setitem__(number, handler))
    def validation(_):
        assert 'app:id/login' in path.read_text()
        assert registry.read_bytes() == registry_before
        handlers[signal.SIGTERM](signal.SIGTERM, None)
    monkeypatch.setattr(heal, '_run_pytest_single', validation)
    with pytest.raises(SystemExit) as cancelled:
        heal.main()
    assert cancelled.value.code == 128 + signal.SIGTERM
    assert path.read_bytes() == original
    assert registry.read_bytes() == registry_before


@pytest.mark.parametrize('surface', ['native', 'webview'])
def test_heal_accepts_current_generator_output(tmp_path, monkeypatch, surface):
    import ast
    heal = load_script('06_heal')
    generate = load_script('02_generate')
    registry = {'targets': {'login.username': {'android': {
        'surface': surface, 'strategy': 'ID', 'value': 'username',
        'webview': {'strategy': 'label', 'value': 'username'},
    }}}}
    monkeypatch.setattr(generate, 'load_registry', lambda: registry)
    source = generate.generate_test_file({
        'tc_number': '001', 'tc_slug': 'login', 'title': '로그인',
        'precondition': '', 'tc_blocks': [{
            'function_name': 'test_login', 'steps': ['username 필드를 확인한다'],
            'expected': 'username', 'selectors': {'username': 'username'},
        }],
    }, 'android')
    path = tmp_path / 'tc_001_login.py'
    path.write_text(source)
    registry_path = tmp_path / 'locators.json'
    registry_path.write_text(json.dumps(registry))
    monkeypatch.setattr(heal, 'CONFIG_DIR', tmp_path)
    monkeypatch.setattr(heal, 'load_registry', lambda: json.loads(registry_path.read_text()))
    monkeypatch.setattr(heal, 'save_registry', lambda value: registry_path.write_text(json.dumps(value)))
    observed = []
    def validate(file):
        tree = ast.parse(Path(file).read_text())
        assignments = {node.targets[0].id: node.value for node in tree.body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        if surface == 'native':
            observed.append(ast.literal_eval(assignments['SEL_USERNAME']))
            assert observed[-1] == 'app:id/username'
            surfaces = ast.literal_eval(assignments['LOCATOR_SURFACES'])
            assert surfaces['app:id/username']['surface'] == 'native'
            assert 'username' not in surfaces
        else:
            observed.append(ast.literal_eval(assignments['LOCATOR_SURFACES'])['username']['webview']['value'])
            assert observed[-1] == 'username-new'
        return True
    monkeypatch.setattr(heal, '_run_pytest_single', validate)
    result = heal.heal_file_xml(str(path), {'login': {'android': {
        'xml': '<node resource-id="app:id/username"/>',
        'webviews': [{'html': '<input aria-label="username-new"/>'}],
    }}})
    assert 'strategy' in result
    assert len(observed) == 1
    stored = json.loads(registry_path.read_text())['targets']['login.username']['android']
    assert (stored['value'] if surface == 'native' else stored['webview']['value']) == observed[0]


def test_selector_literals_support_quotes_parentheses_and_escapes():
    heal = load_script('06_heal')
    source = "SEL_ONE = 'one'\nSEL_TWO = (\n    \"two\\\"quote\"\n)\n"
    assert heal._find_sel_constants(source) == [
        {'const': 'SEL_ONE', 'value': 'one'},
        {'const': 'SEL_TWO', 'value': 'two"quote'},
    ]
    patched = heal._replace_sel_value_and_strategy(source, 'SEL_TWO', 'new"quote', 'ACCESSIBILITY_ID')
    compile(patched, 'literal.py', 'exec')
    assert heal._find_sel_constants(patched)[1]['value'] == 'new"quote'
