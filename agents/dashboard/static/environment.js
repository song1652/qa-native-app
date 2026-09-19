// ── ENV 상태 카드 (Appium + Android + iOS) ────────────────────────
var _envAppiumStatus = 'stopped'; // 상태값 직접 참조용 모듈 변수
var _envAppiumRenderToken = 0;
var _envAppiumActionBusy = false;
var _envAppiumLogState = null;

function pollEnvStatus() {
  fetch('/api/env/status')
    .then(function(r){ return r.json(); })
    .then(function(d){
      updateEnvAppiumCard(d.appium || {});
      updateAndroidCard(d.android || {});
      updateIosCard(d.ios || {});
    })
    .catch(function(){ /* 서버 미응답 시 무시 */ });
}

function updateEnvAppiumCard(appium) {
  var status = appium.status || 'stopped';
  var renderToken = ++_envAppiumRenderToken;
  var topDot = document.getElementById('dot-appium');
  var topText = document.getElementById('txt-appium');
  var appiumReady = status === 'managed' || status === 'external';
  if (topDot) topDot.className = 'dot ' + (appiumReady ? 'on' : 'off');
  if (topText) {
    topText.textContent = appiumReady
      ? 'Appium 연결됨'
      : (status === 'starting' ? 'Appium 시작 중' : (status === 'error' ? 'Appium 오류' : 'Appium 미기동'));
  }
  var card = document.getElementById('env-appium-card');
  if (card) card.setAttribute('data-state', status);

  var badgeMap = {
    stopped: '중지됨',
    starting: '시작 중',
    managed: '실행 중',
    external: '외부 실행 중',
    error: '오류',
  };
  var badge = document.getElementById('env-appium-badge');
  if (badge) badge.textContent = badgeMap[status] || badgeMap.stopped;

  var port = appium.port || 4723;
  var endpoint = document.getElementById('env-appium-endpoint');
  if (endpoint) endpoint.textContent = 'localhost:' + port;

  var owner = document.getElementById('env-appium-owner');
  var ownerText = 'stopped';
  if (status === 'managed') ownerText = 'managed' + (appium.pid ? ' (PID ' + appium.pid + ')' : '');
  else if (status === 'external') ownerText = 'external';
  else if (status === 'starting') ownerText = 'starting' + (appium.pid ? ' (PID ' + appium.pid + ')' : '');
  else if (status === 'error') ownerText = 'error';
  if (owner) owner.textContent = ownerText;

  var version = document.getElementById('env-appium-version');
  if (version) version.textContent = appium.version ? 'Appium ' + appium.version : '확인 전';
  var sessions = document.getElementById('env-appium-sessions');
  if (sessions) sessions.textContent = Number(appium.active_sessions || 0) + '개';
  var uptime = document.getElementById('env-appium-uptime');
  if (uptime) uptime.textContent = formatEnvDuration(appium.uptime_seconds);

  var noteMap = {
    stopped: '아래 시작 버튼을 누르면 필요한 옵션을 포함해 Appium 서버를 자동으로 실행합니다.',
    starting: 'Appium 응답을 기다리는 중입니다. 3초마다 확인하며 최대 30초까지 기다립니다.',
    managed: '이 대시보드가 시작한 Appium입니다. 여기에서 안전하게 중지하거나 재시작할 수 있습니다.',
    external: '터미널 등 외부에서 실행 중인 Appium입니다. 중지 버튼으로 종료할 수 있습니다.',
    error: 'Appium을 시작하지 못했습니다. 아래 오류와 로그를 확인한 뒤 다시 시도해 주세요.',
  };
  var note = document.getElementById('env-appium-state-note');
  if (note) note.textContent = noteMap[status] || noteMap.stopped;

  renderEnvAppiumDriver('uiautomator2', 'UiAutomator2', appium.drivers || {});
  renderEnvAppiumDriver('xcuitest', 'XCUITest', appium.drivers || {});
  renderEnvAppiumDriverHelp(appium.drivers || {});

  var errDiv = document.getElementById('env-appium-error');
  if (errDiv) {
    if (status === 'error' && appium.error_msg) {
      errDiv.textContent = appium.error_msg;
      errDiv.style.display = 'block';
    } else {
      errDiv.style.display = 'none';
    }
  }

  var mjpegPanel = document.getElementById('env-appium-mjpeg-panel');
  if (mjpegPanel) {
    mjpegPanel.classList.remove('warning');
    if (status === 'managed' && appium.mjpeg_enabled !== false) {
      mjpegPanel.textContent = '✓ Android MJPEG 스트리밍 필수 플래그가 설정됨';
      mjpegPanel.style.display = 'block';
    } else if (status === 'external') {
      mjpegPanel.textContent = 'MJPEG 플래그를 확인하고 있습니다...';
      mjpegPanel.style.display = 'block';
      fetch('/api/check/mjpeg?port=8093')
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (renderToken !== _envAppiumRenderToken) return;
          mjpegPanel.classList.toggle('warning', !d.ok);
          mjpegPanel.textContent = d.ok
            ? '✓ 외부 Appium의 MJPEG 스트림을 확인했습니다.'
            : '⚠ MJPEG 플래그를 확인해 주세요. Android 화면 미러링이 동작하지 않을 수 있습니다.';
        })
        .catch(function(){
          if (renderToken !== _envAppiumRenderToken) return;
          mjpegPanel.classList.add('warning');
          mjpegPanel.textContent = '⚠ MJPEG 플래그 상태를 확인하지 못했습니다.';
        });
    } else {
      mjpegPanel.style.display = 'none';
    }
  }

  var btnCfg = {
    'env-btn-start':   status === 'stopped',
    'env-btn-stop':    status === 'managed' || status === 'external',
    'env-btn-restart': status === 'managed',
    'env-btn-refresh': status === 'external',
    'env-btn-retry':   status === 'error',
  };
  Object.keys(btnCfg).forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = btnCfg[id] ? '' : 'none';
  });
  var stopButton = document.getElementById('env-btn-stop');
  if (stopButton) {
    stopButton.textContent = '■ 중지';
    stopButton.disabled = _envAppiumActionBusy;
  }

  var logSection = document.getElementById('env-appium-log-section');
  if (logSection) {
    var showLog = status === 'managed' || status === 'error';
    logSection.style.display = showLog ? 'block' : 'none';
    if (showLog && _envAppiumLogState !== status) {
      _envAppiumLogState = status;
      loadEnvAppiumLog(renderToken);
    } else if (!showLog) {
      _envAppiumLogState = null;
    }
  }

  // 모듈 변수에 상태값 저장 (Android/iOS 카드 게이팅용)
  _envAppiumStatus = status;

  // Android/iOS 파이프라인 버튼 게이팅
  var appiumReady = (status === 'managed' || status === 'external');
  ['btn-run-all','btn-analyze','btn-generate','btn-lint','btn-execute','btn-heal'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el && !el.classList.contains('running')) {
      el.disabled = !appiumReady;
    }
  });
}

function formatEnvDuration(seconds) {
  if (seconds === null || seconds === undefined || isNaN(Number(seconds))) return '—';
  var total = Math.max(0, Math.floor(Number(seconds)));
  var hours = Math.floor(total / 3600);
  var minutes = Math.floor((total % 3600) / 60);
  var secs = total % 60;
  return [hours, minutes, secs].map(function(value){ return String(value).padStart(2, '0'); }).join(':');
}

function renderEnvAppiumDriver(key, label, drivers) {
  var el = document.querySelector('[data-driver="' + key + '"]');
  if (!el) return;
  var ready = drivers[key] === true;
  el.classList.toggle('is-ready', ready);
  el.classList.toggle('is-missing', !ready);
  el.textContent = (ready ? '✓ ' : '✕ ') + label;
}

function renderEnvAppiumDriverHelp(drivers) {
  var help = document.getElementById('env-appium-driver-help');
  if (!help) return;
  var commands = [];
  if (drivers.uiautomator2 !== true) commands.push('appium driver install uiautomator2');
  if (drivers.xcuitest !== true) commands.push('appium driver install xcuitest');
  if (!commands.length) {
    help.style.display = 'none';
    help.textContent = '';
    return;
  }
  help.textContent = '설치되지 않은 드라이버가 있습니다. 최초 환경 구축 시 아래 명령을 복사해 터미널에서 실행하세요.';
  commands.forEach(function(command) {
    var row = document.createElement('div');
    row.className = 'env-appium-driver-command';
    var code = document.createElement('code');
    code.textContent = command;
    var copyButton = document.createElement('button');
    copyButton.type = 'button';
    copyButton.className = 'env-appium-copy';
    copyButton.textContent = '명령 복사';
    copyButton.dataset.copyCommand = command;
    copyButton.addEventListener('click', function(){ copyEnvCommand(copyButton); });
    row.appendChild(code);
    row.appendChild(copyButton);
    help.appendChild(row);
  });
  help.style.display = 'block';
}

async function copyEnvCommand(button) {
  var command = button.dataset.copyCommand || '';
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(command);
    } else {
      legacyCopyEnvCommand(command);
    }
    button.textContent = '복사됨';
    setTimeout(function(){ button.textContent = '명령 복사'; }, 1600);
  } catch (_error) {
    try {
      legacyCopyEnvCommand(command);
      button.textContent = '복사됨';
      setTimeout(function(){ button.textContent = '명령 복사'; }, 1600);
    } catch (_fallbackError) {
      button.textContent = '직접 선택';
    }
  }
}

function legacyCopyEnvCommand(command) {
  var textarea = document.createElement('textarea');
  textarea.value = command;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
}

function loadEnvAppiumLog(renderToken, lines, outputId) {
  var output = document.getElementById(outputId || 'env-appium-log-output');
  if (!output) return;
  output.textContent = '로그를 불러오는 중...';
  fetch('/api/env/appium/log?lines=' + (lines || 200))
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (renderToken !== _envAppiumRenderToken && !outputId) return;
      output.textContent = d.ok && Array.isArray(d.lines) && d.lines.length
        ? d.lines.join('\n')
        : '아직 기록된 Appium 로그가 없습니다.';
      output.scrollTop = output.scrollHeight;
    })
    .catch(function(){
      if (renderToken === _envAppiumRenderToken || outputId) output.textContent = '로그를 불러오지 못했습니다.';
    });
}

function refreshEnvAppiumLog() {
  loadEnvAppiumLog(_envAppiumRenderToken, 200, 'env-appium-log-output');
}

function openEnvAppiumLogModal() {
  var modal = document.getElementById('env-appium-log-modal');
  if (!modal) return;
  modal.style.display = 'flex';
  loadEnvAppiumLog(_envAppiumRenderToken, 200, 'env-appium-log-modal-output');
}

function closeEnvAppiumLogModal() {
  var modal = document.getElementById('env-appium-log-modal');
  if (modal) modal.style.display = 'none';
}

async function envAppiumAction(action) {
  if (_envAppiumActionBusy) return;

  var isStart = action === 'start';
  var isManagedAction = action === 'restart';
  if (isManagedAction && _envAppiumStatus !== 'managed') {
    showEnvAppiumActionError('대시보드가 관리 중인 Appium에서만 재시작할 수 있습니다.');
    return;
  }
  if (isStart && _envAppiumStatus !== 'stopped' && _envAppiumStatus !== 'error') return;

  _envAppiumActionBusy = true;
  setEnvAppiumActionBusy(true);
  clearEnvAppiumActionError();
  try {
    if (action === 'restart') {
      await requestEnvAppium('/api/env/appium/stop');
      await requestEnvAppium('/api/env/appium/start');
    } else {
      await requestEnvAppium(
        action === 'start' ? '/api/env/appium/start' : '/api/env/appium/stop'
      );
    }
    setTimeout(pollEnvStatus, 250);
  } catch (error) {
    showEnvAppiumActionError(friendlyEnvAppiumError(error.code, error.message));
  } finally {
    _envAppiumActionBusy = false;
    setEnvAppiumActionBusy(false);
  }
}

async function requestEnvAppium(url) {
  var response;
  var payload = {};
  try {
    response = await fetch(url, { method: 'POST' });
    payload = await response.json();
  } catch (error) {
    var networkError = new Error('서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
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

function friendlyEnvAppiumError(code, fallback) {
  var messages = {
    capture_session_active: 'Capture 세션이 실행 중입니다. Capture Studio에서 세션을 먼저 종료해 주세요.',
    pipeline_running: '파이프라인이 실행 중입니다. 실행을 마치거나 중단한 뒤 다시 시도해 주세요.',
    external_process: '외부에서 실행한 Appium은 대시보드에서 종료할 수 없습니다.',
    already_running: 'Appium이 이미 실행 중입니다. 상태 새로고침으로 현재 상태를 확인해 주세요.',
    not_running: '종료할 Appium 프로세스를 찾지 못했습니다. 상태를 새로고침해 주세요.',
  };
  return messages[code] || fallback || 'Appium 요청을 처리하지 못했습니다.';
}

function showEnvAppiumActionError(message) {
  var error = document.getElementById('env-appium-error');
  if (!error) return;
  error.textContent = message;
  error.style.display = 'block';
}

function clearEnvAppiumActionError() {
  var error = document.getElementById('env-appium-error');
  if (!error) return;
  error.textContent = '';
  error.style.display = 'none';
}

function setEnvAppiumActionBusy(busy) {
  var card = document.getElementById('env-appium-card');
  if (card) card.setAttribute('aria-busy', busy ? 'true' : 'false');
  ['env-btn-start','env-btn-stop','env-btn-restart','env-btn-refresh','env-btn-retry'].forEach(function(id) {
    var button = document.getElementById(id);
    if (button) button.disabled = busy;
  });
}
