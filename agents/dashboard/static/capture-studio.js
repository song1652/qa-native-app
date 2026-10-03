// ── Capture Studio ────────────────────────────────────────────
var _cs = {
  sessionId: '',
  platform: 'android',       // 현재 세션 플랫폼 ('android' | 'ios')
  recording: false,
  context: 'native',
  actions: [],
  approvedLocators: [],
  selectedNodeAttrs: null,
  mirrorConnected: false,
  mirrorGeneration: 0,
  wsTimeline: null,
  screenshotMode: 'mjpeg',   // 'mjpeg' | 'poll'
  mjpegPort: 8093,           // MJPEG 포트 (iOS: 9100, Android: 8093)
  launching: false,          // Appium/WDA 중복 실행 요청 방지
  pollTimer: null,            // iOS polling setInterval handle
  screenWatcher: null,        // 화면 전환 감지 타이머
  screenHash: null,           // 마지막으로 확인한 page_source 해시
  screenHashTs: 0,            // 마지막 hierarchy 새로고침 시각
};

// Server retries reads within 18s; the browser gives each read 20s without replay.
function csCaptureRead(url, options) {
  var controller = new AbortController();
  var timer = setTimeout(function(){ controller.abort(); }, 20000);
  return fetch(url, Object.assign({}, options, {signal: controller.signal}))
    .then(function(response){
      var readJson = response.json.bind(response);
      response.json = function(){ return readJson().finally(function(){ clearTimeout(timer); }); };
      return response;
    }, function(error){ clearTimeout(timer); throw error; });
}
var _csAliveRead = null;
function csDriverAlive() {
  if(!_csAliveRead) {
    _csAliveRead = csCaptureRead('/capture/driver_alive').then(function(r){ return r.json(); })
      .finally(function(){ _csAliveRead = null; });
  }
  return _csAliveRead;
}
function csRecoveryFailure(data) {
  if(!data.recovery && !data.reconnect_required) return false;
  csLaunchFailed((data.recovery && data.recovery.message) || '기기 연결이 끊겼습니다. 작성 내용은 유지됩니다.',
    (data.recovery && data.recovery.action) || 'reconnect_capture');
  return true;
}

// ── 화면 전환 감지기 ─────────────────────────────────────────────
// 4초마다 page_source 해시를 확인 → 변경되면 hierarchy 자동 새로고침
// hierarchy 새로고침이 최근 3초 이내에 있었으면 스킵 (중복 방지)
function csStartScreenWatcher() {
  csStopScreenWatcher();
  _cs.screenHash = null;
  _cs.screenHashTs = 0;
  var generation = _cs.mirrorGeneration;
  var checking = false;
  _cs.screenWatcher = setInterval(function() {
    if (!_cs.sessionId || _cs.launching || checking) return;
    checking = true;
    csCaptureRead('/capture/page_source_hash')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(generation !== _cs.mirrorGeneration) return;
        if(csRecoveryFailure(d)) return;
        if (!d.ok || !d.hash) return;
        if (_cs.screenHash && _cs.screenHash !== d.hash) {
          // 화면이 바뀜 — hierarchy 새로고침 (쿨다운 3초)
          var now = Date.now();
          if (now - _cs.screenHashTs > 3000) {
            _cs.screenHashTs = now;
            csRefreshHierarchy();
          }
        }
        _cs.screenHash = d.hash;
      })
      .catch(function(){
        if(generation === _cs.mirrorGeneration) csLaunchFailed("서버 연결을 확인한 뒤 세션 재연결을 눌러주세요. 작성 내용은 유지됩니다.");
      }).finally(function(){ checking = false; });
  }, 4000);
}
function csStopScreenWatcher() {
  if (_cs.screenWatcher) { clearInterval(_cs.screenWatcher); _cs.screenWatcher = null; }
  _cs.screenHash = null;
}

// CSS grid align-items:stretch가 높이 동기화를 담당하므로 JS sync 불필요

function csPlatformToggle() {
  var isIos = document.getElementById('cs-platform').value === 'ios';
  // Android 전용 필드
  ['cs-field-pkg', 'cs-field-activity', 'cs-field-mjpeg-port'].forEach(function(id){
    var el = document.getElementById(id);
    if(el) el.style.display = isIos ? 'none' : '';
  });
  // iOS 전용 필드
  ['cs-field-bundle-id', 'cs-field-device-name'].forEach(function(id){
    var el = document.getElementById(id);
    if(el) el.style.display = isIos ? '' : 'none';
  });
  csTargetChanged();
}

var _csEnvGeneration = 0;
var _csDeviceGeneration = 0;
function csTargetMode(platform, target) {
  return target === 'device' ? 'real_device' : (platform === 'ios' ? 'simulator' : 'emulator');
}
function csTargetUnavailable(platform, target) {
  return target === 'device'
    ? '선택한 실기기가 연결되지 않았습니다. 실기기를 연결하거나 실행 대상을 변경한 뒤 환경 확인을 눌러 주세요.'
    : '선택한 ' + (platform === 'ios' ? '시뮬레이터' : '에뮬레이터') + '가 실행 중이 아닙니다. 환경 설정에서 가상 기기를 시작하거나 실행 대상을 변경한 뒤 환경 확인을 눌러 주세요.';
}
function csTargetDevices(platform, target) {
  return fetch('/api/devices?platform=' + encodeURIComponent(platform)).then(function(r){ return r.json(); }).then(function(d){
    if(!Array.isArray(d.devices)) throw new Error('기기 상태를 확인할 수 없습니다. 환경 확인을 다시 눌러 주세요.');
    return d.devices.filter(function(device){ return device.mode === csTargetMode(platform, target); });
  });
}
function csConnectedTarget(devices, platform) {
  var nameEl = document.getElementById('cs-device-name');
  var name = platform === 'ios' && nameEl ? nameEl.value : '';
  var connected = devices.filter(function(d){ return d.connected && d.udid && (!name || d.deviceName === name); });
  return connected.find(function(d){ return d.default; }) || connected[0];
}
function csTargetChanged() {
  var generation = ++_csEnvGeneration;
  document.getElementById('cs-start-btn').disabled = true;
  var status = document.getElementById('cs-setup-status');
  status.textContent = '선택한 실행 대상의 환경 확인을 눌러 주세요.';
  status.style.color = 'var(--text3)';
  var platform = document.getElementById('cs-platform').value;
  var target = document.getElementById('cs-target').value;
  var deviceGeneration = ++_csDeviceGeneration;
  if(platform !== 'ios') return;
  var select = document.getElementById('cs-device-name');
  var previous = select.dataset.restoreName || select.value || '';
  delete select.dataset.restoreName;
  select.innerHTML = '';
  csTargetDevices(platform, target).then(function(devices){
    if(deviceGeneration !== _csDeviceGeneration) return;
    devices.forEach(function(d){
      var option = document.createElement('option');
      option.value = d.deviceName || '';
      option.textContent = d.deviceName || d.udid || '이름 없는 기기';
      option.selected = d.deviceName === previous || (!previous && d.default);
      select.appendChild(option);
    });
  }).catch(function(error){
    if(generation === _csEnvGeneration) status.textContent = error.message;
  });
}

function csInit() {
  // Capture 탭 선택 시 세션 상태 복원
  fetch('/capture/session').then(function(r){ return r.json(); }).then(function(d){
    if(d.active && d.session){
      _cs.sessionId = d.session.session_id || '';
      _cs.actions = csRestoreActionDraft(_cs.sessionId, d.session.actions);
      _cs.platform = d.session.platform || 'android';
      var port = d.session.mjpeg_port || (_cs.platform === 'ios' ? 9100 : 8093);
      _cs.mjpegPort = port;
      _cs.screenshotMode = d.session.screenshot_mode || 'mjpeg';
      if(_cs.sessionId){
        // OS 복원 및 폼 토글
        var platEl = document.getElementById('cs-platform');
        var savedPlatform = d.session.platform || 'android';
        if(platEl) platEl.value = savedPlatform;
        var targetEl = document.getElementById('cs-target');
        if(targetEl) targetEl.value = d.session.target || 'emulator';
        var restoredNameEl = document.getElementById('cs-device-name');
        if(restoredNameEl) restoredNameEl.dataset.restoreName = d.session.device_name || '';
        csPlatformToggle();
        // 폼 값 복원
        var pkgEl = document.getElementById('cs-pkg');
        var actEl = document.getElementById('cs-activity');
        var grpEl = document.getElementById('cs-group');
        var portEl = document.getElementById('cs-mjpeg-port');
        var bundleEl = document.getElementById('cs-bundle-id');
        var devNameEl = document.getElementById('cs-device-name');
        if(pkgEl && !pkgEl.value) pkgEl.value = d.session.app_package || '';
        if(actEl && !actEl.value) actEl.value = d.session.app_activity || '';
        if(grpEl && !grpEl.value) grpEl.value = d.session.tc_group || '';
        if(portEl) portEl.value = port;
        if(bundleEl && !bundleEl.value) bundleEl.value = d.session.bundle_id || '';
        if(devNameEl && !devNameEl.value) devNameEl.value = d.session.device_name || '';

        // 드라이버 상태 확인 후 분기
        csDriverAlive().then(function(d2){
          var statusEl2 = document.getElementById('cs-setup-status');
          if(d2.alive){
            // 드라이버 살아있음 → workspace로 이동
            document.getElementById('cs-setup').style.display='none';
            document.getElementById('cs-workspace').style.display='block';
            document.getElementById('cs-session-badge').style.display='';
            var _rPlatform = (d && d.session && d.session.platform) || 'android';
            var _rDevice = (d && d.session && d.session.device_name) || '';
            var _rGroup = (d && d.session && d.session.tc_group) || '';
            csInfoStripShow(_rPlatform, _rDevice, _rGroup);
            csRenderTimeline();
            csMirrorConnect();
            csStartScreenWatcher();
            var saveStatus = document.getElementById('cs-save-status');
            if(saveStatus){ saveStatus.textContent = ' 세션 복원됨 (드라이버 연결)'; saveStatus.style.color='var(--pass)'; }
            setTimeout(function(){ csRefreshHierarchy(); }, 600);
          } else {
            // 드라이버 죽음 → setup 화면 유지, 안내 메시지 + 버튼 표시
            if(statusEl2){
              statusEl2.innerHTML = ' 이전 작성 내용이 보관되어 있습니다. 기기 연결을 확인하고 같은 기기로 재연결하세요.<br>'
                + '<div style="margin-top:6px;display:flex;gap:8px">'
                + '<button class="cs-btn primary" onclick="csReLaunchFromSetup()" style="padding:4px 14px;font-size:11px">▶ 앱 재실행</button>'
                + '<button class="cs-btn" onclick="csForceNewSession()" style="padding:4px 14px;font-size:11px;color:var(--text3)">새 세션 시작</button>'
                + '</div>';
              statusEl2.style.color='var(--warn)';
              if(d2.recovery){
                statusEl2.replaceChildren();
                var guidance = document.createElement('p');
                guidance.textContent = d2.recovery.message;
                statusEl2.appendChild(guidance);
                csRecoveryControl(statusEl2, d2.recovery.action, csReLaunchFromSetup);
              }
            }
            document.getElementById('cs-session-badge').style.display='';
          }
        }).catch(function(){
          // driver_alive 호출 실패 → 그냥 setup 화면 유지
        });
      }
    }
  }).catch(function(){});
  csMcpStartPoll();
}

function csReLaunch() {
  var saveStatus = document.getElementById('cs-save-status');
  if(_cs.launching){
    if(saveStatus){ saveStatus.textContent = '앱 실행이 진행 중입니다. 서버 응답을 기다려 주세요.'; saveStatus.style.color='var(--accent)'; }
    return;
  }
  _cs.launching = true;
  csMirrorDisconnect();
  csStopScreenWatcher();
  var sessionId = _cs.sessionId;
  var _reIsIos = (_cs.platform === 'ios' || _cs.screenshotMode === 'poll');
  var _reTimeoutMs = _reIsIos ? 420000 : 130000;
  var _reStartTs = Date.now();
  saveStatus.textContent = ' 앱 재실행 중...'; saveStatus.style.color='var(--accent)';
  var _reProgressTimer = setInterval(function(){
    if(sessionId !== _cs.sessionId) { clearInterval(_reProgressTimer); return; }
    var s = Math.round((Date.now() - _reStartTs) / 1000);
    saveStatus.textContent = ' 앱 재실행 중… (' + s + '초 경과' + (_reIsIos ? ' / 서버 응답 대기 최대 420초' : '') + ')';
  }, 2000);
  var _launchCtrl = new AbortController();
  var _launchTimer = setTimeout(function(){ _launchCtrl.abort(); }, _reTimeoutMs);
  fetch('/capture/launch', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sessionId}),
    signal: _launchCtrl.signal
  }).then(function(r){ clearTimeout(_launchTimer); clearInterval(_reProgressTimer); return r.json(); }).then(function(d){
    if(sessionId !== _cs.sessionId) return;
    _cs.launching = false;
    if(d.ok){
      // 세션 만료 배너 제거
      var _eb = document.getElementById('cs-expired-banner');
      if(_eb) _eb.remove();
      saveStatus.textContent = ' 앱 재실행됨 — 미러링 재연결 중';
      saveStatus.style.color='var(--pass)';
      csMirrorConnect();
      csStartScreenWatcher();
      setTimeout(csRefreshHierarchy, 1500);
    } else {
      if(!csRecoveryFailure(d)) csLaunchFailed(' 재실행 실패: ' + (d.error||'알 수 없는 오류'));
    }
  }).catch(function(err){
    clearTimeout(_launchTimer); clearInterval(_reProgressTimer);
    if(sessionId !== _cs.sessionId) return;
    _cs.launching = false;
    var s2 = Math.round((Date.now() - _reStartTs) / 1000);
    saveStatus.textContent = err && err.name==='AbortError'
      ? ' 재실행 ' + s2 + '초 초과 — 서버에서 실행이 계속 진행 중일 수 있습니다. 상태를 확인한 후 재연결하세요.'
      : ' 오류: ' + err;
    saveStatus.style.color='var(--fail)';
    csLaunchFailed(saveStatus.textContent);
  });
}

var _obsLastRunId = null;  // 가장 최근 obs_run_start에서 받은 run_id

function csHandleTimelineEvent(evt) {
  // 관측성: obs_run_start 이벤트 → run_id 캡처
  if(evt.type === 'obs_run_start' && evt.run_id){
    _obsLastRunId = evt.run_id;
  }
  // 관측성: obs_run_summary 이벤트 → 증거 버튼 주입
  if(evt.type === 'obs_run_summary' && evt.run_id){
    _obsLastRunId = evt.run_id;
    // localStorage에도 저장해 새로고침 후 복원 가능
    try{ localStorage.setItem('qa-native-app.obs-last-run-id.'+_quickPlatform, evt.run_id); }catch(_){}
    setTimeout(function(){ _obsInjectEvidenceButtons(evt.run_id); }, 2500);
  }
  // Livetail 연동: source 필드가 있는 이벤트를 csLtAppend에 전달
  if(evt.source){
    var src     = evt.source;
    var type    = evt.type || evt.action || 'event';
    var summary = evt.summary || evt.locator || '';
    var result  = evt.ok === false ? 'fail' : 'ok';
    var ms      = evt.duration_ms ? evt.duration_ms + 'ms' : '';
    csLtAppend(src, type, evt.platform || '', summary, result, ms);
  }
  // Capture 타임라인 액션은 명시적 녹화 중에만 반영한다.
  if(!_cs.recording)return;
  if(evt.type === 'action_added' && evt.action){
    _cs.actions.push(evt.action);
    csRenderTimeline();
  }
}

var _wsReconnectDelay = 1000;
function csConnectWsTimeline() {
  if(_cs.wsTimeline && _cs.wsTimeline.readyState < 2) return;
  try {
    var ws = new WebSocket('ws://localhost:' + location.port + '/ws/timeline');
    ws.onopen = function(){ _wsReconnectDelay = 1000; };
    ws.onmessage = function(e) {
      try {
        var evt = JSON.parse(e.data);
        csHandleTimelineEvent(evt);
      } catch(err){}
    };
    ws.onclose = function(){
      _cs.wsTimeline = null;
      // 지수 백오프 재연결 (최대 30초)
      setTimeout(csConnectWsTimeline, _wsReconnectDelay);
      _wsReconnectDelay = Math.min(_wsReconnectDelay * 2, 30000);
    };
    _cs.wsTimeline = ws;
    // keepalive ping
    setInterval(function(){ if(_cs.wsTimeline && _cs.wsTimeline.readyState===1) _cs.wsTimeline.send('ping'); }, 20000);
  } catch(err){
    setTimeout(csConnectWsTimeline, _wsReconnectDelay);
    _wsReconnectDelay = Math.min(_wsReconnectDelay * 2, 30000);
  }
}

function csCheckEnv() {
  var statusEl = document.getElementById('cs-setup-status');
  statusEl.textContent = '환경 확인 중...';
  statusEl.style.color = 'var(--text3)';
  var platform = document.getElementById('cs-platform').value;
  var isIos = platform === 'ios';

  var target = document.getElementById('cs-target').value;
  var generation = ++_csEnvGeneration;
  document.getElementById('cs-start-btn').disabled = true;
  var checks = [
    csTargetDevices(platform, target).catch(function(){ return []; }),
    fetch('/api/check/appium').then(function(r){ return r.json(); }).catch(function(){ return {ok:false}; }),
  ];
  if(!isIos) {
    var port = parseInt(document.getElementById('cs-mjpeg-port').value) || 8093;
    checks.push(fetch('/api/check/mjpeg?port=' + port).then(function(r){ return r.json(); }).catch(function(){ return {ok:false}; }));
  }

  return Promise.all(checks).then(function(results) {
    if(generation !== _csEnvGeneration) return;
    var device = csConnectedTarget(results[0], platform);
    var appiumOk = results[1].ok;
    var msgs = [];
    if(appiumOk) msgs.push(' Appium 연결됨');
    else msgs.push(' Appium 미응답 (appium --address 127.0.0.1 --port 4723)');

    if(!isIos) {
      var port2 = parseInt(document.getElementById('cs-mjpeg-port').value) || 8093;
      var mjpegOk = results[2] && results[2].ok;
      if(mjpegOk) msgs.push(' MJPEG 포트 ' + port2 + ' 응답');
      else msgs.push(' MJPEG 포트 미응답 — 세션 시작 후 활성화됩니다 (--allow-insecure=uiautomator2:adb_screen_streaming 필요)');
    } else {
      msgs.push('iOS는 screenshot polling 방식 사용 (MJPEG 불필요)');
    }

    msgs.push(device ? '선택한 실행 대상 연결됨: ' + device.deviceName : csTargetUnavailable(platform, target));
    statusEl.textContent = msgs.join('\n');
    statusEl.style.whiteSpace = 'pre-line';
    statusEl.style.color = appiumOk && device ? 'var(--pass)' : 'var(--fail)';
    document.getElementById('cs-start-btn').disabled = !appiumOk || !device;
  });
}

function csStartSession() {
  var platform = document.getElementById('cs-platform').value;
  var isIos = platform === 'ios';
  var target = document.getElementById('cs-target').value;
  var selectionGeneration = _csEnvGeneration;
  var selectedName = document.getElementById('cs-device-name').value;
  function selectionUnchanged() {
    return selectionGeneration === _csEnvGeneration
      && platform === document.getElementById('cs-platform').value
      && target === document.getElementById('cs-target').value
      && (!isIos || selectedName === document.getElementById('cs-device-name').value);
  }
  var group = document.getElementById('cs-group').value.trim();
  var mjpegPort = parseInt(document.getElementById('cs-mjpeg-port').value) || 8093;

  var body;
  if(isIos) {
    var bundleId = document.getElementById('cs-bundle-id').value.trim();
    var deviceName = document.getElementById('cs-device-name').value.trim() || 'iPhone Simulator';
    if(!bundleId){ alert('Bundle ID를 입력하세요.'); return; }
    group = group || bundleId.split('.').pop() || 'default';
    body = {platform: platform, target: target, bundle_id: bundleId, device_name: deviceName, tc_group: group};
  } else {
    var pkg = document.getElementById('cs-pkg').value.trim();
    var activity = document.getElementById('cs-activity').value.trim();
    if(!pkg){ alert('App Package를 입력하세요.'); return; }
    group = group || pkg.split('.').pop() || 'default';
    body = {platform: platform, target: target, app_package: pkg, app_activity: activity, tc_group: group, mjpeg_port: mjpegPort};
  }

  var statusEl = document.getElementById('cs-setup-status');
  if(_cs.launching){
    statusEl.textContent = ' 앱 실행이 이미 진행 중입니다. 잠시 기다려 주세요.';
    statusEl.style.color = 'var(--accent)';
    return;
  }
  _cs.launching = true;
  statusEl.textContent = '세션 시작 중...';
  document.getElementById('cs-start-btn').disabled = true;

  csTargetDevices(platform, target).then(function(devices){
    if(!selectionUnchanged()) {
      throw new Error('실행 대상이 변경되었습니다. 환경 확인을 다시 눌러 주세요.');
    }
    var device = csConnectedTarget(devices, platform);
    if(!device) throw new Error(csTargetUnavailable(platform, target));
    body.udid = device.udid;
    body.device_name = device.deviceName;
    return fetch('/capture/session', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)
    });
  }).then(function(r){ return r.json(); }).then(function(d){
    if(d.ok && !selectionUnchanged()){
      _cs.launching = false;
      _cs.sessionId = d.session_id;
      _cs.platform = platform;
      document.getElementById('cs-start-btn').disabled = true;
      statusEl.textContent = '실행 대상이 변경되어 앱 실행을 취소했습니다. 생성된 세션을 종료한 뒤 새 대상을 확인해 주세요.';
      statusEl.style.color = 'var(--warn)';
      var resetButton = document.createElement('button');
      resetButton.className = 'cs-btn';
      resetButton.textContent = '세션 종료 후 새 세션 준비';
      resetButton.onclick = csForceNewSession;
      statusEl.appendChild(document.createElement('br'));
      statusEl.appendChild(resetButton);
      return;
    }
    if(d.ok){
      _cs.sessionId = d.session_id;
      _cs.platform = isIos ? 'ios' : 'android';
      _cs.actions = [];
      _cs.screenshotMode = d.screenshot_mode || 'mjpeg';
      _cs.mjpegPort = d.mjpeg_port || (isIos ? 9100 : 8093);
      window._csDeviceWidth  = d.device_width  || 1080;
      window._csDeviceHeight = d.device_height || 1920;
      var _mjpegUrlEl = document.getElementById('cs-mjpeg-url');
      if(_mjpegUrlEl) _mjpegUrlEl.textContent = d.mjpeg_url || ('http://localhost:' + _cs.mjpegPort);
      csRenderTimeline();

      // ── 앱 실행 단계 ──
      // WDA 180초 대기 × 2회와 서버 응답 여유를 포함한다.
      var _launchTimeoutMs = isIos ? 420000 : 130000;
      var _launchStartTs   = Date.now();

      // iOS 대기 중 경과 시간을 실시간으로 표시 (매 2초 갱신)
      var _launchProgressTimer = null;
      function _updateLaunchStatus() {
        if(d.session_id !== _cs.sessionId) { clearInterval(_launchProgressTimer); return; }
        var elapsed = Math.round((Date.now() - _launchStartTs) / 1000);
        if (isIos) {
          statusEl.textContent = ' iOS 앱 실행 중… WDA 초기화 대기 중 (' + elapsed + '초 경과 / 서버 응답 대기 최대 420초)';
        } else {
          statusEl.textContent = ' 앱 실행 중… (' + elapsed + '초 경과)';
        }
        statusEl.style.color = 'var(--accent)';
      }
      _updateLaunchStatus();
      _launchProgressTimer = setInterval(_updateLaunchStatus, 2000);

      var _launchCtrl = new AbortController();
      var _launchTimer = setTimeout(function(){ _launchCtrl.abort(); }, _launchTimeoutMs);
      fetch('/capture/launch', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({session_id: d.session_id}),
        signal: _launchCtrl.signal
      }).then(function(r2){ clearTimeout(_launchTimer); clearInterval(_launchProgressTimer); return r2.json(); }).then(function(d2){
        if(d.session_id !== _cs.sessionId) return;
        _cs.launching = false;
        if(d2.ok){
          // launch 응답에서 MJPEG 포트 업데이트 (iOS: 9100, Android: 8093)
          if(d2.mjpeg_port) _cs.mjpegPort = d2.mjpeg_port;
          if(d2.screenshot_mode) _cs.screenshotMode = d2.screenshot_mode;
          var modeLabel = 'MJPEG 스트리밍';
          var elapsed2 = Math.round((Date.now() - _launchStartTs) / 1000);
          statusEl.textContent = ' 앱 실행됨 (Appium: ' + (d2.appium_session_id||'').substring(0,8) + '...) — ' + modeLabel + ' 시작 (' + elapsed2 + '초)';
          statusEl.style.color = 'var(--pass)';
          // 워크스페이스 전환
          document.getElementById('cs-setup').style.display='none';
          document.getElementById('cs-workspace').style.display='block';
          document.getElementById('cs-session-badge').style.display='';
          var _devLabel = isIos ? (document.getElementById('cs-device-name') ? document.getElementById('cs-device-name').value.trim() : '') : (d2.device_name || '');
          csInfoStripShow(platform, _devLabel, group);
          // MJPEG 미러 연결
          csMirrorConnect();
          // 초기 hierarchy 로드
          setTimeout(function(){ csRefreshHierarchy(); }, 1500);
          // 화면 전환 자동 감지 시작
          setTimeout(csStartScreenWatcher, 3000);
          // MCP 상태 폴링 시작
          csMcpStartPoll();
        } else {
          // 백엔드가 이미 친화적 메시지를 반환 (_friendly_appium_error) → 그대로 표시
          var errMsg = (d2.recovery && d2.recovery.message) || d2.error || '알 수 없는 오류가 발생했습니다.';
          statusEl.textContent = ' 앱 실행 실패: ' + errMsg;
          statusEl.style.color = 'var(--fail)';
          // 세션은 생성됐으므로 워크스페이스는 진입 허용
          document.getElementById('cs-setup').style.display='none';
          document.getElementById('cs-workspace').style.display='block';
          document.getElementById('cs-session-badge').style.display='';
          var _devLabel = isIos ? (document.getElementById('cs-device-name') ? document.getElementById('cs-device-name').value.trim() : '') : (d2.device_name || '');
          csInfoStripShow(platform, _devLabel, group);
          if(!csRecoveryFailure(d2)) csLaunchFailed(statusEl.textContent);
        }
      }).catch(function(err2){
        clearTimeout(_launchTimer);
        clearInterval(_launchProgressTimer);
        if(d.session_id !== _cs.sessionId) return;
        _cs.launching = false;
        var elapsed3 = Math.round((Date.now() - _launchStartTs) / 1000);
        var msg;
        if (err2 && err2.name === 'AbortError') {
          msg = isIos
            ? ' iOS WDA 초기화 ' + elapsed3 + '초 초과 — 서버에서 실행이 계속 진행 중일 수 있습니다. 상태를 확인한 후 재연결하세요.'
            : ' 앱 실행 ' + elapsed3 + '초 초과 — Appium 서버와 에뮬레이터 상태를 확인하세요';
        } else {
          msg = ' 앱 실행 오류: ' + err2;
        }
        statusEl.textContent = msg;
        statusEl.style.color = 'var(--warn)';
        document.getElementById('cs-setup').style.display='none';
        document.getElementById('cs-workspace').style.display='block';
        document.getElementById('cs-session-badge').style.display='';
        var _devLabelCatch = isIos ? (document.getElementById('cs-device-name') ? document.getElementById('cs-device-name').value.trim() : '') : '';
        csInfoStripShow(platform, _devLabelCatch, group);
        document.getElementById('cs-start-btn').disabled = false;
        csLaunchFailed(msg);
      });
    } else {
      _cs.launching = false;
      statusEl.textContent = ' ' + (d.error || '세션 시작 실패');
      statusEl.style.color = 'var(--fail)';
      document.getElementById('cs-start-btn').disabled = true;
    }
  }).catch(function(err){
    _cs.launching = false;
    statusEl.textContent = err.message || String(err);
    statusEl.style.color = 'var(--fail)';
    document.getElementById('cs-start-btn').disabled = true;
  });
}

function csMirrorDisconnect() {
  ++_cs.mirrorGeneration;
  _cs.mirrorConnected = false;
  if(_cs.pollTimer) { clearInterval(_cs.pollTimer); _cs.pollTimer = null; }
  csSubStatusConn(false);
  var img = document.getElementById('cs-mirror-img');
  if(img) { img.onload = img.onerror = null; img.removeAttribute('src'); img.style.display = 'none'; }
}

function csRecoveryControl(container, action, reconnect) {
  if(!action || action === 'reconnect_capture') {
    var retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'cs-btn primary';
    retry.textContent = '세션 재연결';
    retry.onclick = reconnect;
    container.appendChild(retry);
  } else {
    var link = document.createElement('a');
    link.className = 'cs-btn';
    var environment = ['check_environment', 'review_configuration'].includes(action);
    link.href = environment ? '/?view=config' : '/?view=history';
    link.textContent = environment ? '환경 설정 확인' : '실행 기록 확인';
    container.appendChild(link);
  }
}

function csLaunchFailed(message, action) {
  csMirrorDisconnect();
  csStopScreenWatcher();
  var status = document.getElementById('cs-save-status');
  if(status) { status.textContent = message; status.style.color = 'var(--fail)'; }
  var placeholder = document.getElementById('cs-mirror-placeholder');
  if(placeholder) {
    placeholder.querySelectorAll('.cs-mirror-error, .cs-mirror-loading').forEach(function(el){ el.remove(); });
    var error = document.createElement('div');
    error.className = 'cs-mirror-error';
    error.setAttribute('role', 'alert');
    error.style.cssText = 'color:var(--fail);padding:12px;white-space:pre-wrap';
    error.textContent = message + '\n';
    csRecoveryControl(error, action, csReLaunch);
    placeholder.appendChild(error);
    placeholder.style.display = '';
  }
}

function csMirrorConnect() {
  var img = document.getElementById('cs-mirror-img');
  var placeholder = document.getElementById('cs-mirror-placeholder');
  var generation = ++_cs.mirrorGeneration;
  _cs.mirrorConnected = false;
  csSubStatusConn(false);

  // 기존 polling 타이머 정리
  if(_cs.pollTimer) { clearInterval(_cs.pollTimer); _cs.pollTimer = null; }

  if(_cs.screenshotMode === 'poll') {
    // ── iOS polling 방식 ──────────────────────────────────────
    img.onerror = null;
    img.onload = null;
    // 첫 스크린샷 수신 전까지 로딩 표시 (img는 숨김)
    img.style.display = 'none';
    var _existingErr = placeholder.querySelector('.cs-mirror-error');
    if(_existingErr) _existingErr.remove();
    var _loadDiv = placeholder.querySelector('.cs-mirror-loading');
    if(!_loadDiv){
      _loadDiv = document.createElement('div');
      _loadDiv.className = 'cs-mirror-loading';
      _loadDiv.style.cssText = 'color:var(--text3);text-align:center;padding:12px;font-size:11px';
      _loadDiv.innerHTML = 'iOS 화면 로딩 중...<br><span style="font-size:10px">WDA 안정화 대기</span>';
      placeholder.appendChild(_loadDiv);
    }
    placeholder.style.display = '';

    var _pollFailCount = 0;
    var _POLL_FAIL_THRESHOLD = 25; // 25회 연속 실패 후 에러 표시 (약 30초 — WDA 안정화 여유)
    var _firstFrame = true;
    var _pollBusy = false;

    function doPoll() {
      if(_pollBusy || generation !== _cs.mirrorGeneration || _cs.launching) return;
      _pollBusy = true;
      csCaptureRead('/capture/screenshot').then(function(r){ return r.json(); }).then(function(d){
        if(generation !== _cs.mirrorGeneration) return;
        if(csRecoveryFailure(d)) return;
        if(d.ok && d.data){
          _cs.mirrorConnected = true;
          csSubStatusConn(true);
          _pollFailCount = 0; // 성공 시 실패 카운터 초기화
          img.src = 'data:image/png;base64,' + d.data;
          // 첫 프레임 수신 시 로딩 제거 후 img 표시
          if(_firstFrame){
            _firstFrame = false;
            var ld = placeholder.querySelector('.cs-mirror-loading');
            if(ld) ld.remove();
          }
          placeholder.style.display = 'none';
          img.style.display = 'block';
          // 에러 오버레이 자동 제거 (self-healing)
          var prev = placeholder.querySelector('.cs-mirror-error');
          if(prev) prev.remove();
        } else {
          _cs.mirrorConnected = false;
          csSubStatusConn(false);
          _pollFailCount++;
          // 임계값 초과 시에만 에러 UI 표시 (로딩 표시도 제거)
          if(_pollFailCount >= _POLL_FAIL_THRESHOLD){
            img.style.display = 'none';
            placeholder.style.display = '';
            var ld2 = placeholder.querySelector('.cs-mirror-loading');
            if(ld2) ld2.remove();
            var prev2 = placeholder.querySelector('.cs-mirror-error');
            if(!prev2){
              var errDiv = document.createElement('div');
              errDiv.className = 'cs-mirror-error';
              errDiv.style.cssText = 'color:var(--fail);text-align:center;padding:12px';
              errDiv.innerHTML = ' iOS 스크린샷 실패<br>'
                + '<span style="font-size:10px;color:var(--text3)">Appium 세션이 끊겼습니다</span><br><br>'
                + '<button class="cs-btn primary" onclick="csReLaunch()" style="padding:4px 12px;font-size:11px;margin-bottom:4px"> 세션 재연결</button><br>'
                + '<button class="cs-btn" onclick="csMirrorConnect()" style="padding:4px 12px;font-size:11px"> 미러링만 재시도</button>';
              placeholder.appendChild(errDiv);
            }
          }
          // 임계값 미만: 로딩 표시 유지, 에러 오버레이 없음
        }
      }).catch(function(){
        if(generation !== _cs.mirrorGeneration) return;
        _cs.mirrorConnected = false;
        csSubStatusConn(false);
        _pollFailCount++;
      }).finally(function(){ _pollBusy = false; });
    }
    doPoll();
    _cs.pollTimer = setInterval(doPoll, 1200);

  } else {
    // ── MJPEG / ffmpeg 스트리밍 ────────────────────────────────
    // iOS: AVFoundation ffmpeg 스트림 (/capture/stream/ios)
    // Android: Appium MJPEG (포트 8093)
    var platform = _cs.platform || 'android';
    var ts = new Date().getTime();
    var streamUrl;
    if(platform === 'ios') {
      streamUrl = '/capture/stream/ios?' + ts;
    } else {
      var port = _cs.mjpegPort || parseInt(document.getElementById('cs-mjpeg-port').value) || 8093;
      streamUrl = 'http://localhost:' + port + '/?' + ts;
    }

    img.onerror = function() {
      _cs.mirrorConnected = false;
      csSubStatusConn(false);
      img.style.display = 'none';
      placeholder.style.display = '';
      var prev = placeholder.querySelector('.cs-mirror-error');
      if(prev) prev.remove();
      var errDiv = document.createElement('div');
      errDiv.className = 'cs-mirror-error';
      errDiv.style.cssText = 'color:var(--fail);text-align:center;padding:12px';
      var errDetail = platform === 'ios'
        ? '화면 녹화 권한 또는 ffmpeg 오류'
        : 'MJPEG 포트 ' + (port || 8093) + ' 미응답';
      errDiv.innerHTML = ' 미러링 연결 실패<br>'
        + '<span style="font-size:10px;color:var(--text3)">' + errDetail + '</span><br><br>'
        + '<button class="cs-btn primary" onclick="csReLaunch()" style="padding:4px 12px;font-size:11px;margin-bottom:4px"> 세션 재연결</button><br>'
        + '<button class="cs-btn" onclick="csMirrorConnect()" style="padding:4px 12px;font-size:11px"> 미러링만 재시도</button>';
      placeholder.appendChild(errDiv);
    };
    img.onload = function() {
      if(generation !== _cs.mirrorGeneration) return;
      _cs.mirrorConnected = true;
      placeholder.style.display = 'none';
      img.style.display = 'block';
      csSubStatusConn(true);
    };
    img.src = streamUrl;
    img.style.display = 'none';
    placeholder.style.display = '';
  }
}

function _csMirrorDevicePoint(img, x, y) {
  var rect = img.getBoundingClientRect();
  var dims = _csGetDeviceDimensions();
  var width = img.naturalWidth || dims.w;
  var height = img.naturalHeight || dims.h;
  if(!rect.width || !rect.height || !width || !height) return null;
  var scale = Math.min(rect.width / width, rect.height / height);
  var visibleW = width * scale, visibleH = height * scale;
  x -= (rect.width - visibleW) / 2;
  y -= (rect.height - visibleH) / 2;
  if(x < 0 || y < 0 || x >= visibleW || y >= visibleH) return null;
  return {x: Math.round(x * dims.w / visibleW), y: Math.round(y * dims.h / visibleH), w: dims.w};
}

function csMirrorClick(event) {
  var img = document.getElementById('cs-mirror-img');
  var rect = img.getBoundingClientRect();
  var imgX = event.clientX - rect.left;
  var imgY = event.clientY - rect.top;
  var point = _csMirrorDevicePoint(img, imgX, imgY);
  if(!point) return;

  // 십자선 표시
  var ch = document.getElementById('cs-crosshair');
  if (ch) { ch.style.display='block'; ch.style.left=imgX+'px'; ch.style.top=imgY+'px'; }

  // 디바이스 실제 너비: _csGetDeviceDimensions() 로 통합 읽기 (Android/iOS 공통)
  var displayW = point.w;
  var _hierLoaded = !!_csHierarchyDom;

  // hierarchy 미로드 시 좌표 기본값(1080) 사용 — 사용자에게 알림
  if (!_hierLoaded) {
    csStatusMsg(' Hierarchy가 로드되지 않았습니다. 좌표가 부정확할 수 있습니다 — 잠시 후 Hierarchy 새로고침을 눌러주세요.');
  }

  var devX = point.x;
  var devY = point.y;

  // Hierarchy에서 해당 좌표 노드 찾아 트리 하이라이트 + element detail 업데이트
  if (_csHierarchyDom) {
    var hitNode = csFindSmallestNodeAt(devX, devY, _csHierarchyDom.documentElement);
    if (hitNode) csHighlightNodeInTree(hitNode);
  }

  // iOS 탭 처리 중 오버레이 (polling 지연 시각화, 최대 2초)
  var _isIosTap = (document.getElementById('cs-platform').value === 'ios');
  var _tapOverlay = document.getElementById('cs-ios-tap-overlay');
  var _tapOverlayTimer = null;
  if (_isIosTap && _tapOverlay) {
    _tapOverlay.style.display = 'flex';
    _tapOverlayTimer = setTimeout(function(){ _tapOverlay.style.display = 'none'; }, 2000);
  }

  // 미러 클릭은 항상 Appium에 탭 전달 (녹화 상태 무관)
  fetch('/capture/tap', {
    method:'POST', headers:{'Content-Type':'application/json'},
    // 이미 디바이스 좌표로 변환했으므로 서버의 추가 배율은 1이다.
    body: JSON.stringify({session_id:_cs.sessionId, x:devX, y:devY, img_width:displayW, display_width:displayW, context:_cs.context})
  }).then(function(r){ return r.json(); }).then(function(d){
    if (_tapOverlay && _tapOverlayTimer) { clearTimeout(_tapOverlayTimer); _tapOverlay.style.display = 'none'; }
    if (!d.ok) {
      csStatusMsg(' ' + (d.error || 'tap 실패'));
    }
  }).catch(function(err){
    if (_tapOverlay && _tapOverlayTimer) { clearTimeout(_tapOverlayTimer); _tapOverlay.style.display = 'none'; }
    csStatusMsg('오류: ' + err);
  });
}
