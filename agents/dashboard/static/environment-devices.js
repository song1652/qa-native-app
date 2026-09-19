// ── Android / iOS 디바이스 카드 ──────────────────────────────────
// US-3: 에뮬레이터/시뮬레이터 목록 렌더링 (삭제 버튼 포함)
function envAttr(value) {
  return esc(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderDeviceList(containerId, devices, platform, mode, runtime) {
  var el = document.getElementById(containerId);
  if (!el) return;
  if (!devices || devices.length === 0) {
    el.innerHTML = '<div class="env-device-empty">등록된 ' + (platform === 'android' ? '에뮬레이터' : '시뮬레이터') + '가 없습니다.</div>';
    return;
  }
  runtime = runtime || {};
  var platformBusy = _envDeviceActionBusy[platform];
  var runtimeBusy = runtime.status === 'starting';
  var runtimeRunning = runtime.status === 'running';
  el.innerHTML = devices.map(function(dev) {
    var name = dev.deviceName || '이름 없음';
    var sub = dev.avd || dev.udid || '';
    var isDefault = dev['default'];
    var isActive = platform === 'android'
      ? !!dev.avd && dev.avd === runtime.avd
      : (!!dev.udid && dev.udid === runtime.udid) || (!runtime.udid && dev.deviceName === runtime.simulator);
    var rowState = isActive && runtimeBusy ? ' is-starting' : (isActive && runtimeRunning ? ' is-active' : '');
    var version = (platform === 'android' ? 'Android ' : 'iOS ') + (dev.platformVersion || '버전 확인 필요');
    var action = isActive && runtimeRunning ? 'stop' : 'start';
    var actionText = action === 'stop' ? (platform === 'android' ? '■ 중지' : '■ 종료') : (platform === 'android' ? '▶ 시작' : '▶ 부팅');
    var actionLabel = name + ' ' + (action === 'stop' ? (platform === 'android' ? '중지' : '종료') : (platform === 'android' ? '시작' : '부팅'));
    var actionDisabled = platformBusy || runtimeBusy || (runtimeRunning && !isActive);
    var isLastVirtual = (mode !== 'real_device') && devices.length <= 1;
    var rmTooltip = isLastVirtual ? '마지막 기기입니다. 다른 기기를 먼저 추가하면 삭제할 수 있습니다.' : (name + ' 삭제');
    return '<div class="env-device-row' + rowState + '" data-device-key="' + encodeURIComponent(sub) + '">'
      + '<div class="env-device-main"><span class="env-device-dot" aria-hidden="true"></span><div class="env-device-copy">'
      + '<div class="env-device-name"><strong>' + esc(name) + '</strong><span class="env-device-version">' + esc(version) + '</span>'
      + (isDefault ? '<span class="env-default-badge">기본</span>' : '') + '</div>'
      + '<div class="env-device-key">' + esc(sub) + '</div></div></div>'
      + '<div class="env-device-actions">'
      + '<button class="env-row-action' + (action === 'stop' ? ' stop' : '') + '" type="button" aria-label="' + envAttr(actionLabel) + '" data-env-platform="' + platform + '" data-env-action="' + action + '" data-env-target="' + encodeURIComponent(sub) + '" onclick="envVirtualActionFromButton(this)"' + (actionDisabled ? ' disabled' : '') + '>' + actionText + '</button>'
      + '<button class="env-row-remove" type="button" aria-label="' + envAttr(rmTooltip) + '" title="' + envAttr(rmTooltip) + '" data-platform="' + encodeURIComponent(platform) + '" data-mode="' + encodeURIComponent(mode) + '" data-device-name="' + encodeURIComponent(name) + '" onclick="envRemoveDeviceFromButton(this)"' + (isLastVirtual ? ' disabled' : '') + '>×</button>'
      + '</div>'
      + '</div>';
  }).join('');
}

function renderRealDevices(containerId, realDevices, platform) {
  var el = document.getElementById(containerId);
  if (!el) return;
  if (!realDevices || realDevices.length === 0) {
    el.innerHTML = '<span style="font-size:11px;color:var(--text3)">등록된 실기기 없음</span>';
    return;
  }
  el.innerHTML = realDevices.map(function(dev) {
    var dot = dev.connected
      ? '<span style="color:var(--pass)">&#9679;</span>'
      : '<span style="color:var(--text3)">&#9679;</span>';
    var label = dev.deviceName || dev.serial || dev.udid || '알 수 없음';
    var sub = dev.serial || dev.udid || '';
    var wifiBtns = '';
    if (dev.wifi_ip) {
      var btnStyle = 'padding:3px 10px;font-size:11px;border-radius:4px;border:1px solid var(--border);background:var(--surface);color:var(--text1);cursor:pointer;';
      if (dev.connected) {
        wifiBtns = '<button onclick="envAndroidRealDisconnect()" style="' + btnStyle + '">&#9986; 해제</button>';
      } else {
        wifiBtns = '<button onclick="envAndroidRealConnect()" style="' + btnStyle + '">&#128279; WiFi</button>';
      }
    }
    var isLastReal = realDevices.length <= 1;
    var delBtn = platform
      ? '<button data-platform="' + encodeURIComponent(platform) + '" data-mode="real_device" data-device-name="' + encodeURIComponent(label) + '" data-is-last="' + isLastReal + '" onclick="envRemoveDeviceFromButton(this)" '
        + 'style="font-size:10px;color:var(--fail);background:none;border:none;cursor:pointer;padding:0 4px" title="삭제">&#10005;</button>'
      : '';
    return '<div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;font-size:12px;flex-wrap:wrap">'
      + dot + ' <span>' + esc(label) + '</span>'
      + (sub ? '<span style="color:var(--text3);font-size:10px;font-family:monospace">' + esc(sub) + '</span>' : '')
      + (wifiBtns ? '<span style="margin-left:4px">' + wifiBtns + '</span>' : '')
      + delBtn
      + '</div>';
  }).join('');
}

// ── US-3: 디바이스 추가/삭제 ─────────────────────────────────────

var _envAddCtx = {platform: '', mode: '', devices: [], trigger: null};
var _envConfiguredVirtual = {android: {}, ios: {}};

function showEnvAddError(message) {
  var error = document.getElementById('env-add-error');
  error.textContent = message || '';
  error.style.display = message ? 'block' : 'none';
}

function envUserErrorMessage(data, fallback) {
  var messages = {
    duplicate_avd: '이미 등록된 Android 에뮬레이터입니다.',
    duplicate_udid: '이미 등록된 iOS 시뮬레이터입니다.',
    duplicate_deviceName: '같은 이름의 시뮬레이터가 이미 등록되어 있습니다.',
    invalid_avd: '이 컴퓨터에서 찾을 수 없는 Android 에뮬레이터입니다. 목록을 새로고침해 주세요.',
    invalid_udid: '이 컴퓨터에서 찾을 수 없는 iOS 시뮬레이터입니다. 목록을 새로고침해 주세요.',
    capture_session_active: 'Capture Studio가 이 기기를 사용 중입니다. 먼저 Capture 세션을 종료해 주세요.',
    pipeline_running: '파이프라인이 실행 중입니다. 끝난 뒤 다시 시도해 주세요.'
  };
  return (data && (data.message || messages[data.error] || data.detail || data.error)) || fallback;
}

function envSelectDiscoveredDevice() {
  var select = document.getElementById('env-add-device-select');
  var selected = _envAddCtx.devices.find(function(device) {
    return (_envAddCtx.platform === 'android' ? device.avd : device.udid) === select.value;
  });
  document.getElementById('env-add-deviceName').value = selected ? (selected.deviceName || '') : '';
  document.getElementById('env-add-platformVersion').value = selected ? (selected.platformVersion || '') : '';
  document.getElementById('env-add-avd').value = selected && selected.avd ? selected.avd : '';
  document.getElementById('env-add-udid').value = selected && selected.udid ? selected.udid : '';
  document.getElementById('env-add-register').disabled = !selected || !selected.platformVersion;
}

function loadEnvVirtualDevices(platform) {
  var select = document.getElementById('env-add-device-select');
  var register = document.getElementById('env-add-register');
  select.innerHTML = '<option value="">불러오는 중...</option>';
  select.disabled = true;
  register.disabled = true;
  var url = platform === 'android'
    ? '/api/env/android/list_system_avds'
    : '/api/env/ios/list_system_simulators';
  fetch(url)
    .then(function(response) { return response.json().then(function(data) { return {response:response, data:data}; }); })
    .then(function(result) {
      if (!result.response.ok || result.data.ok === false) throw new Error(result.data.message || result.data.error || '목록을 불러오지 못했습니다.');
      _envAddCtx.devices = platform === 'android' ? (result.data.avds || []) : (result.data.simulators || []);
      if (!_envAddCtx.devices.length) {
        select.innerHTML = '<option value="">설치된 기기가 없습니다</option>';
        showEnvAddError(platform === 'android' ? 'Android Studio에서 AVD를 먼저 만들어 주세요.' : 'Xcode에서 시뮬레이터를 먼저 만들어 주세요.');
        return;
      }
      var configured = _envConfiguredVirtual[platform] || {};
      var firstUnregistered = '';
      select.innerHTML = _envAddCtx.devices.map(function(device) {
        var value = platform === 'android' ? device.avd : device.udid;
        var label = device.deviceName + ' (' + (platform === 'android' ? 'Android ' : 'iOS ') + (device.platformVersion || '?') + ')';
        if (configured[value]) label += ' · 등록됨';
        else if (!firstUnregistered) firstUnregistered = value;
        return '<option value="' + encodeURIComponent(value) + '">' + esc(label) + '</option>';
      }).join('');
      Array.prototype.forEach.call(select.options, function(option) {
        option.value = decodeURIComponent(option.value);
      });
      select.disabled = false;
      if (firstUnregistered) select.value = firstUnregistered;
      envSelectDiscoveredDevice();
      select.focus();
    })
    .catch(function(error) {
      _envAddCtx.devices = [];
      select.innerHTML = '<option value="">목록 불러오기 실패</option>';
      showEnvAddError(error.message || '목록을 불러오지 못했습니다.');
    });
}

function envShowAddModal(platform, mode) {
  _envAddCtx = {platform: platform, mode: mode, devices: [], trigger: document.activeElement};
  var modeLabel = {emulator:'에뮬레이터', real_device:'실기기', simulator:'시뮬레이터'}[mode] || mode;
  var platformLabel = platform === 'android' ? 'Android' : 'iOS';
  var virtualDevice = mode === 'emulator' || mode === 'simulator';
  document.getElementById('env-add-modal-title').textContent = (platform === 'android' ? '🤖 ' : '🍎 ') + platformLabel + ' ' + modeLabel + ' 추가';
  document.getElementById('env-add-discovery-row').style.display = virtualDevice ? '' : 'none';
  document.getElementById('env-add-version-row').style.display = virtualDevice ? '' : 'none';
  document.getElementById('env-add-udid-row').style.display = (mode === 'simulator' || mode === 'real_device') ? '' : 'none';
  document.getElementById('env-add-default-row').style.display = virtualDevice ? 'none' : '';
  document.getElementById('env-add-select-label').textContent = platform === 'android' ? '시스템에 설치된 AVD (emulator -list-avds)' : '시뮬레이터 선택 (xcrun simctl list)';
  document.getElementById('env-add-name-label').textContent = platform === 'android' ? '이름 (자동 입력)' : (mode === 'simulator' ? '기기명 (자동 입력)' : '기기명');
  document.getElementById('env-add-version-label').textContent = platform === 'android' ? 'Android 버전 (자동 입력)' : 'iOS 버전 (자동 입력)';
  document.getElementById('env-add-udid-label').textContent = mode === 'simulator' ? 'UDID (자동 입력)' : 'Serial / UDID';
  document.getElementById('env-add-deviceName').value = '';
  document.getElementById('env-add-deviceName').readOnly = virtualDevice;
  document.getElementById('env-add-platformVersion').value = '';
  document.getElementById('env-add-platformVersion').readOnly = virtualDevice;
  document.getElementById('env-add-avd').value = '';
  document.getElementById('env-add-udid').value = '';
  document.getElementById('env-add-udid').readOnly = mode === 'simulator';
  document.getElementById('env-add-default').checked = false;
  showEnvAddError('');
  document.getElementById('env-add-modal').style.display = 'flex';
  if (virtualDevice) {
    loadEnvVirtualDevices(platform);
  } else {
    document.getElementById('env-add-register').disabled = false;
    document.getElementById('env-add-deviceName').focus();
  }
}

function envCloseAddModal() {
  document.getElementById('env-add-modal').style.display = 'none';
  var trigger = _envAddCtx.trigger;
  if (trigger && typeof trigger.focus === 'function') trigger.focus();
}

async function envSubmitAddDevice() {
  var platform = _envAddCtx.platform;
  var mode = _envAddCtx.mode;
  var body = {
    mode: mode,
    deviceName: document.getElementById('env-add-deviceName').value.trim(),
  };
  if (mode === 'emulator') {
    body.avd = document.getElementById('env-add-avd').value.trim();
    body.platformVersion = document.getElementById('env-add-platformVersion').value.trim();
  } else if (mode === 'simulator') {
    body.platformVersion = document.getElementById('env-add-platformVersion').value.trim();
    body.udid = document.getElementById('env-add-udid').value.trim();
  } else if (mode === 'real_device') {
    body.udid = document.getElementById('env-add-udid').value.trim();
    body['default'] = document.getElementById('env-add-default').checked;
  }
  var register = document.getElementById('env-add-register');
  register.disabled = true;
  showEnvAddError('');
  try {
    var response = await fetch('/api/env/' + platform + '/add', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    var data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(envUserErrorMessage(data, '등록하지 못했습니다.'));
    envCloseAddModal();
    setTimeout(pollEnvStatus, 200);
  } catch (error) {
    showEnvAddError(error.message || '대시보드 서버에 연결할 수 없습니다.');
    register.disabled = false;
  }
}

document.addEventListener('keydown', function(event) {
  var modal = document.getElementById('env-add-modal');
  if (event.key === 'Escape' && modal && modal.style.display !== 'none') envCloseAddModal();
});

var _ENV_REMOVE_ERROR_MAP = {
  last_device: '마지막 기기는 삭제할 수 없습니다. 다른 기기를 먼저 추가하세요.',
  capture_session_active: 'Capture Studio 세션이 활성 상태입니다. 먼저 세션을 종료하세요.',
  pipeline_running: '파이프라인 실행 중에는 디바이스를 변경할 수 없습니다.',
  'device not found': '이미 삭제된 기기입니다. 목록을 새로고침합니다.',
};
function envRemoveErrorMsg(error) {
  return _ENV_REMOVE_ERROR_MAP[error] || ('삭제 실패: ' + (error || '알 수 없는 오류'));
}
function envConfirmRemoveDevice(platform, mode, deviceName, isLastReal) {
  return new Promise(function(resolve) {
    var dialog = document.createElement('dialog');
    dialog.className = 'report-delete-dialog';
    var title = isLastReal ? '마지막 실기기 삭제' : '기기 삭제';
    var warning = isLastReal
      ? '<br><span style="color:var(--fail);font-size:12px">이 기기를 삭제하면 '
        + (platform === 'android' ? 'Android' : 'iOS')
        + ' 실기기 실행이 불가해집니다.</span>'
      : '';
    var typeNote = mode !== 'real_device'
      ? '<br><span style="font-size:11px;color:var(--text3)">에뮬레이터/시뮬레이터 자체는 삭제되지 않습니다.</span>'
      : '';
    dialog.innerHTML = '<form method="dialog"><h2>' + esc(title) + '</h2><p>'
      + esc(deviceName) + '을(를) 목록에서 삭제하시겠습니까?' + warning + typeNote
      + '</p><div class="report-dialog-actions"><button value="cancel" autofocus>취소</button>'
      + '<button value="delete" class="report-danger">삭제</button></div></form>';
    dialog.addEventListener('close', function() {
      var ok = dialog.returnValue === 'delete';
      dialog.remove();
      resolve(ok);
    }, {once: true});
    document.body.appendChild(dialog);
    dialog.showModal();
  });
}
function envRemoveDevice(platform, mode, deviceName, isLastReal) {
  envConfirmRemoveDevice(platform, mode, deviceName, !!isLastReal).then(function(ok) {
    if (!ok) return;
    fetch('/api/env/' + platform + '/remove', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode: mode, deviceName: deviceName}),
    })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (!d.ok) {
          var errMsg = envRemoveErrorMsg(d.error);
          var errDlg = document.createElement('dialog');
          errDlg.className = 'report-delete-dialog';
          errDlg.innerHTML = '<form method="dialog"><h2>삭제 실패</h2><p>' + esc(errMsg) + '</p>'
            + '<div class="report-dialog-actions"><button value="ok" autofocus>확인</button></div></form>';
          errDlg.addEventListener('close', function() { errDlg.remove(); }, {once: true});
          document.body.appendChild(errDlg);
          errDlg.showModal();
          if (d.error === 'device not found') setTimeout(pollEnvStatus, 300);
          return;
        }
        setTimeout(pollEnvStatus, 300);
      })
      .catch(function() {});
  });
}

function envRemoveDeviceFromButton(button) {
  return envRemoveDevice(
    decodeURIComponent(button.dataset.platform || ''),
    decodeURIComponent(button.dataset.mode || ''),
    decodeURIComponent(button.dataset.deviceName || ''),
    button.dataset.isLast === 'true'
  );
}

function envAndroidRealConnect() {
  fetch('/api/env/android/real/connect', { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: '{}' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) { alert('연결 실패: ' + (d.error || '알 수 없는 오류')); }
      setTimeout(pollEnvStatus, 1000);
    })
    .catch(function() {});
}

function envAndroidRealDisconnect() {
  fetch('/api/env/android/real/disconnect', { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: '{}' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) { alert('해제 실패: ' + (d.error || '알 수 없는 오류')); }
      setTimeout(pollEnvStatus, 1000);
    })
    .catch(function() {});
}

// ── Phase 3: WiFi 페어링 ─────────────────────────────────────────
function envShowWifiPairModal() {
  document.getElementById('env-pair-ip').value = '';
  document.getElementById('env-pair-port').value = '';
  document.getElementById('env-pair-code').value = '';
  var r = document.getElementById('env-pair-result');
  r.style.display = 'none'; r.textContent = '';
  document.getElementById('env-wifi-pair-modal').style.display = 'flex';
}
function envCloseWifiPairModal() {
  document.getElementById('env-wifi-pair-modal').style.display = 'none';
}
function envSubmitWifiPair() {
  var ip = document.getElementById('env-pair-ip').value.trim();
  var port = document.getElementById('env-pair-port').value.trim();
  var code = document.getElementById('env-pair-code').value.trim();
  if (!ip || !port || !code) { alert('IP, 포트, 코드를 모두 입력하세요.'); return; }
  var r = document.getElementById('env-pair-result');
  r.style.display = 'block';
  r.style.background = 'rgba(245,158,11,.1)'; r.style.border = '1px solid rgba(245,158,11,.3)';
  r.textContent = '페어링 중...';
  fetch('/api/env/android/real/pair', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ip: ip, port: port, code: code})
  }).then(function(resp) { return resp.json(); })
    .then(function(d) {
      if (d.ok) {
        r.style.background = 'rgba(34,197,94,.1)'; r.style.border = '1px solid rgba(34,197,94,.3)';
        r.textContent = '✅ 페어링 성공: ' + (d.detail || '');
        setTimeout(function() { envCloseWifiPairModal(); setTimeout(pollEnvStatus, 500); }, 2000);
      } else {
        r.style.background = 'rgba(251,113,133,.1)'; r.style.border = '1px solid rgba(251,113,133,.3)';
        r.textContent = '❌ 페어링 실패: ' + (d.detail || d.error || '알 수 없는 오류');
      }
    })
    .catch(function() { r.textContent = '❌ 네트워크 오류'; });
}

// ── Phase 3: iOS WDA 빌드 ────────────────────────────────────────
function envShowWdaBuildModal() {
  document.getElementById('env-wda-udid').value = '';
  document.getElementById('env-wda-teamid').value = '';
  var r = document.getElementById('env-wda-result');
  r.style.display = 'none'; r.textContent = '';
  document.getElementById('env-wda-build-modal').style.display = 'flex';
}
function envCloseWdaBuildModal() {
  document.getElementById('env-wda-build-modal').style.display = 'none';
}
function envSubmitWdaBuild() {
  var udid = document.getElementById('env-wda-udid').value.trim();
  var teamId = document.getElementById('env-wda-teamid').value.trim();
  if (!udid || !teamId) { alert('UDID와 Team ID를 모두 입력하세요.'); return; }
  var r = document.getElementById('env-wda-result');
  r.style.display = 'block';
  r.style.background = 'rgba(245,158,11,.1)'; r.style.border = '1px solid rgba(245,158,11,.3)';
  r.textContent = 'WDA 빌드 요청 중...';
  fetch('/api/env/ios/real/wda_build', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({udid: udid, team_id: teamId})
  }).then(function(resp) { return resp.json(); })
    .then(function(d) {
      if (d.ok) {
        r.style.background = 'rgba(34,197,94,.1)'; r.style.border = '1px solid rgba(34,197,94,.3)';
        r.textContent = '✅ ' + (d.detail || 'WDA 빌드 시작됨 (PID: ' + d.pid + ')');
      } else {
        r.style.background = 'rgba(251,113,133,.1)'; r.style.border = '1px solid rgba(251,113,133,.3)';
        r.textContent = '❌ ' + (d.detail || d.error || '빌드 실패');
      }
    })
    .catch(function() { r.textContent = '❌ 네트워크 오류'; });
}

function updateAndroidCard(android) {
  var status = android.status || 'stopped';
  var badgeMap = {
    stopped:  { text: '● 중지됨',    color: 'var(--text3)' },
    starting: { text: '● 부팅 중...', color: 'var(--warn)' },
    running:  { text: '● 실행 중',   color: 'var(--pass)' },
    error:    { text: '● 오류',      color: 'var(--fail)' },
  };
  var info = badgeMap[status] || badgeMap['stopped'];
  var badge = document.getElementById('env-android-badge');
  if (badge) { badge.textContent = info.text.replace('● ', ''); badge.style.color = info.color; }
  if (status === 'error' && android.error_msg) {
    showEnvDeviceError('android', android.error_msg);
  }

  _envConfiguredVirtual.android = {};
  (android.emulators || []).forEach(function(device) {
    if (device.avd) _envConfiguredVirtual.android[device.avd] = true;
  });
  renderDeviceList('env-android-emulator-list', android.emulators || [], 'android', 'emulator', android);

  // 실기기 목록 렌더링 (M3.0 + US-3)
  renderRealDevices('env-android-real-list', android.real_devices || [], 'android');
}

function updateIosCard(ios) {
  var status = ios.status || 'stopped';
  var badgeMap = {
    stopped:  { text: '● 중지됨',    color: 'var(--text3)' },
    starting: { text: '● 부팅 중...', color: 'var(--warn)' },
    running:  { text: '● 실행 중',   color: 'var(--pass)' },
    error:    { text: '● 오류',      color: 'var(--fail)' },
  };
  var info = badgeMap[status] || badgeMap['stopped'];
  var badge = document.getElementById('env-ios-badge');
  if (badge) { badge.textContent = info.text.replace('● ', ''); badge.style.color = info.color; }
  if (status === 'error' && ios.error_msg) {
    showEnvDeviceError('ios', ios.error_msg);
  }

  _envConfiguredVirtual.ios = {};
  (ios.simulators || []).forEach(function(device) {
    if (device.udid) _envConfiguredVirtual.ios[device.udid] = true;
  });
  renderDeviceList('env-ios-simulator-list', ios.simulators || [], 'ios', 'simulator', ios);

  // 실기기 목록 렌더링 (M3.0 + US-3)
  renderRealDevices('env-ios-real-list', ios.real_devices || [], 'ios');
}

var _envDeviceActionBusy = { android: false, ios: false };

async function requestEnvDevice(url, body) {
  var response;
  var payload = {};
  try {
    var options = { method: 'POST' };
    if (body) {
      options.headers = {'Content-Type':'application/json'};
      options.body = JSON.stringify(body);
    }
    response = await fetch(url, options);
    payload = await response.json();
  } catch (_error) {
    var networkError = new Error('서버에 연결할 수 없습니다. 대시보드 서버를 확인해 주세요.');
    networkError.code = 'network_error';
    throw networkError;
  }
  if (!response.ok || payload.ok === false) {
    var requestError = new Error(payload.detail || payload.error || '요청을 처리하지 못했습니다.');
    requestError.code = payload.error || 'request_failed';
    throw requestError;
  }
  return payload;
}

function friendlyEnvDeviceError(code, fallback) {
  var messages = {
    capture_session_active: 'Capture 세션이 실행 중입니다. Capture Studio에서 먼저 종료해 주세요.',
    already_running: '이미 실행 중이거나 시작 중입니다. 상태를 새로고침해 주세요.',
    no_avd_configured: '시작할 Android 에뮬레이터가 없습니다. 먼저 에뮬레이터를 추가해 주세요.',
    no_simulator_configured: '시작할 iOS 시뮬레이터가 없습니다. 먼저 시뮬레이터를 추가해 주세요.',
    emulator_not_found: 'Android Emulator 실행 파일을 찾지 못했습니다. Android SDK 설치를 확인해 주세요.',
    adb_not_found: 'ADB 실행 파일을 찾지 못했습니다. Android SDK 설치를 확인해 주세요.',
  };
  return messages[code] || fallback || '기기 요청을 처리하지 못했습니다.';
}

function showEnvDeviceError(platform, message) {
  var error = document.getElementById('env-' + platform + '-error');
  if (!error) return;
  error.textContent = message;
  error.style.display = 'block';
}

function clearEnvDeviceError(platform) {
  var error = document.getElementById('env-' + platform + '-error');
  if (!error) return;
  error.textContent = '';
  error.style.display = 'none';
}

function setEnvDeviceActionBusy(platform, busy) {
  var card = document.getElementById('env-' + platform + '-card');
  if (card) card.setAttribute('aria-busy', busy ? 'true' : 'false');
  document.querySelectorAll('[data-env-platform="' + platform + '"]').forEach(function(button) {
    button.disabled = busy;
  });
}

async function envDeviceAction(platform, action, target) {
  if (_envDeviceActionBusy[platform]) return;
  _envDeviceActionBusy[platform] = true;
  setEnvDeviceActionBusy(platform, true);
  clearEnvDeviceError(platform);
  var badge = document.getElementById('env-' + platform + '-badge');
  if (badge) {
    badge.textContent = action === 'start' ? '● 시작 요청 중...' : '● 종료 요청 중...';
    badge.style.color = 'var(--warn)';
  }
  var isAndroid = platform === 'android';
  var url = isAndroid
    ? '/api/env/android/avd/' + action
    : '/api/env/ios/simulator/' + action;
  var body = isAndroid ? {avd: target} : {udid: target};
  try {
    await requestEnvDevice(url, target ? body : null);
    if (badge) badge.textContent = '● 요청 완료 · 상태 확인 중...';
    setTimeout(pollEnvStatus, 250);
  } catch (error) {
    showEnvDeviceError(platform, friendlyEnvDeviceError(error.code, error.message));
    pollEnvStatus();
  } finally {
    _envDeviceActionBusy[platform] = false;
    setEnvDeviceActionBusy(platform, false);
  }
}

function envVirtualActionFromButton(button) {
  return envDeviceAction(
    button.dataset.envPlatform,
    button.dataset.envAction,
    decodeURIComponent(button.dataset.envTarget || '')
  );
}
function envAndroidStart(avd) { return envDeviceAction('android', 'start', avd); }
function envAndroidStop(avd) { return envDeviceAction('android', 'stop', avd); }
function envIosStart(udid) { return envDeviceAction('ios', 'start', udid); }
function envIosStop(udid) { return envDeviceAction('ios', 'stop', udid); }
