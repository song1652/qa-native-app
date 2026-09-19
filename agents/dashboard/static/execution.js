// ── 스텝 숫자 상태 ──────────────────────────────────────────
function setStepNum(step, state){
  var el=document.getElementById('sn-'+step);
  if(!el) return;
  el.className='step-num '+(state||'');
  // 진행률 인디케이터 동기화
  var pState = {running:'running', done:'done', failed:'failed', '':'idle'}[state||''] || 'idle';
  setStepState(step, pState);
}

// ── 실행 / 취소 ─────────────────────────────────────────────
var _runAllSteps = ['analyze','generate','lint','execute','heal'];
var _runAllActive = false;
var _runAllStartedAt = 0;
var _runAllFolders = [];
var _runAllPlatform = 'android';
var _runAllHistoryRecorded = false;

// ── 디바이스 선택 상태 ──
var _selectedDevice = null; // {mode, deviceName, udid, connected}

var _devicePickerData = {};

function _renderDeviceList(containerId, hintId, devices, captureSession, platform) {
  var container = document.getElementById(containerId);
  var hintEl    = document.getElementById(hintId);
  if(!container) return;

  _devicePickerData[containerId] = devices;

  var sessionUdid   = captureSession && captureSession.active ? (captureSession.udid || '') : '';
  var sessionTarget = captureSession && captureSession.active ? (captureSession.target || '') : '';

  var autoSelect = null;
  if(sessionUdid) autoSelect = devices.find(function(d){ return d.udid === sessionUdid; });
  if(!autoSelect && sessionTarget) {
    var modeKey = sessionTarget === 'emulator' ? 'emulator' : 'real_device';
    autoSelect = devices.find(function(d){ return d.mode === modeKey && d.connected; });
  }
  if(!autoSelect) {
    autoSelect = devices.find(function(d){ return d.connected && d.default; })
              || devices.find(function(d){ return d.connected; });
  }
  if(autoSelect && (!_selectedDevice || !devices.find(function(d){ return d.udid === _selectedDevice.udid; }))) {
    _selectedDevice = autoSelect;
  }

  if(hintEl) {
    if(autoSelect && captureSession && captureSession.active) {
      hintEl.className = 'device-hint found';
      hintEl.textContent = 'Capture 세션 감지 → ' + autoSelect.deviceName + ' 자동 선택';
      hintEl.style.display = '';
    } else {
      hintEl.className = 'device-hint none';
      hintEl.textContent = 'Capture 세션 없음 — 디바이스를 직접 선택하세요';
      hintEl.style.display = '';
    }
  }

  var emulators   = devices.filter(function(d){ return d.mode === 'emulator' || d.mode === 'simulator'; });
  var realDevices = devices.filter(function(d){ return d.mode === 'real_device'; });

  function cardHtml(d, globalIdx) {
    var isSelected = _selectedDevice && _selectedDevice.udid === d.udid && _selectedDevice.deviceName === d.deviceName;
    var realCls = d.mode === 'real_device' ? ' real' : '';
    var disCls  = d.connected ? '' : ' disconnected';
    var selCls  = isSelected ? ' selected' : '';
    var badge   = d.connected
      ? (d.mode === 'emulator' || d.mode === 'simulator'
          ? '<span class="device-badge running">실행 중</span>'
          : '<span class="device-badge connected">연결됨</span>')
      : '<span class="device-badge offline">미연결</span>';
    var clickAttr = d.connected
      ? ' onclick="selectDeviceCard(this,\'' + containerId + '\',' + globalIdx + ')"'
      : '';
    return '<div class="device-card'+selCls+realCls+disCls+'"'+clickAttr+'>'
      +'<div class="device-radio"><div class="device-radio-dot"></div></div>'
      +'<div class="device-info">'
        +'<div class="device-name">'+esc(d.deviceName || d.udid || '알 수 없음')+'</div>'
        +'<div class="device-meta">'+esc(d.udid || '')+(d.platformVersion?' · '+(platform==='ios'?'iOS':'Android')+' '+esc(d.platformVersion):'')+'</div>'
      +'</div>'+badge+'</div>';
  }

  var html = '';
  if(emulators.length) {
    html += '<div class="device-divider">'+(platform==='ios'?'시뮬레이터':'에뮬레이터')+'</div>';
    html += emulators.map(function(d,i){ return cardHtml(d, i); }).join('');
  }
  if(realDevices.length) {
    html += '<div class="device-divider">실기기</div>';
    html += realDevices.map(function(d,i){ return cardHtml(d, emulators.length + i); }).join('');
  }
  if(!html) html = '<div style="font-size:11px;color:var(--text3)">연결된 디바이스 없음</div>';
  container.innerHTML = html;
}

function selectDeviceCard(el, containerId, idx) {
  var devices = _devicePickerData[containerId];
  if(!devices || idx >= devices.length) return;
  var d = devices[idx];
  _selectedDevice = d;
  var picker = el.closest('.device-picker');
  if(picker) picker.querySelectorAll('.device-card').forEach(function(c){ c.classList.remove('selected'); });
  el.classList.add('selected');
}

function refreshDevicePicker() {
  var qMode = document.body.classList.contains('quick-mode');
  if(qMode) {
    loadDevicePicker(_quickPlatform, 'quick');
  } else {
    loadDevicePicker(getPlatform(), 'pipeline');
  }
}

// target: 'pipeline' | 'quick' | 없으면 둘 다
function loadDevicePicker(platform, target) {
  fetch('/api/devices?platform=' + platform)
    .then(function(r){ return r.json(); })
    .catch(function(){ return {ok:false, devices:[]}; })
    .then(function(data) {
      var devices = (data.ok && data.devices) ? data.devices : [];
      fetch('/capture/session').then(function(r){ return r.json(); }).catch(function(){ return {}; })
        .then(function(sess) {
          var s = sess.session || null;
          if(!target || target === 'pipeline') {
            _renderDeviceList('pipeline-device-list', 'pipeline-device-hint', devices, s, platform);
          }
          if(!target || target === 'quick') {
            _renderDeviceList('quick-device-list', 'quick-device-hint', devices, s, platform);
          }
        });
    });
}

function getSelectedDeviceParams() {
  if(!_selectedDevice) return {};
  return {
    mode: _selectedDevice.mode,
    device_udid: _selectedDevice.udid || '',
  };
}

async function runAll(){
  if(_runAllActive) return;
  _runAllActive = true;
  _runAllStartedAt = Date.now();
  _runAllHistoryRecorded = false;
  var btn = document.getElementById('btn-run-all');
  btn.classList.add('loading');
  btn.disabled = true;
  hideGuideBanner();
  hideFails();
  clearLog();

  // 모든 스텝을 running 표시로 초기화
  _runAllSteps.forEach(function(s){ setStepState(s, 'idle'); });

  var platform = getPlatform();
  var tcFolders = getTcFolders();
  _runAllPlatform = platform;
  _runAllFolders = tcFolders.slice();
  if(!tcFolders.length){ setLog('[안내] 실행할 TC 폴더를 하나 이상 선택하세요.'); _finishRunAll(false); return; }

  try {
    var res = await fetch('/api/run_all', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign({platform: platform, tc_folders: tcFolders, obs_keep: _obsKeep}, getSelectedDeviceParams()))
    });
    var data = await res.json();
    if(!data.ok){
      setLog('[오류] ' + (data.error || '알 수 없는 오류'));
      _finishRunAll(false); return;
    }
  } catch(e){
    setLog('[요청 실패] ' + e.message);
    _finishRunAll(false); return;
  }

  // execute까지 순서대로 폴링, 이후 heal은 로그 감지로 처리
  _pollRunAllStep(0, platform);
}

function _isHealLogActive(healRound){
  // run_heal_1.txt ~ run_heal_3.txt 존재 여부로 heal 활성 감지
  return fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({log: 'run_heal_' + healRound + '.txt'})})
    .then(function(r){ return r.json(); })
    .then(function(d){ return d.ok && d.log.length > 0; })
    .catch(function(){ return false; });
}

function _pollRunAllStep(idx, platform){
  var MAIN_STEPS = ['analyze','generate','lint','execute'];
  if(idx >= MAIN_STEPS.length){
    // execute 완료 후 — state에서 실패 여부 즉시 확인
    _checkNeedHeal(function(needHeal){
      if(needHeal){ _pollHealRounds(1); }
      else { _finishRunAll(true); }
    });
    return;
  }
  var step = MAIN_STEPS[idx];
  var logFiles = {analyze:'run_analyze.txt', generate:'run_generate.txt', lint:'run_lint.txt', execute:'run_execute.txt'};
  _currentLog = logFiles[step];
  _currentStep = step;
  setStepNum(step, 'running');
  setLog('[전체실행] ' + (idx+1) + '/' + MAIN_STEPS.length + ' — ' + step + ' 실행 중...\n');

  var prevLen = 0;
  var timer = setInterval(async function(){
    try {
      var r = await fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({log: logFiles[step]})});
      var d = await r.json();
      if(d.ok && d.log.length !== prevLen){ setLog(d.log); prevLen = d.log.length; }
      if(d.done){
        clearInterval(timer);
        var ok = d.exit_code === 0;
        setStepNum(step, ok ? 'done' : 'failed');
        if(!ok){
          showGuideBanner(step, false);
          _finishRunAll(false);
        } else {
          _pollRunAllStep(idx+1, platform);
        }
      }
    } catch(_){}
  }, 1200);
}

function _checkNeedHeal(cb){
  fetch('/api/state').then(function(r){ return r.json(); }).then(function(st){
    var failed = (((st.execute_results||{}).summary)||{}).failed || 0;
    cb(failed > 0);
  }).catch(function(){ cb(false); });
}

function _pollHealRounds(round){
  if(round > 3){ _finishRunAll(true); return; }
  // heal 로그 파일이 생겼는지 최대 8초 대기 (서버가 즉시 heal 없이 끝났을 수도 있음)
  var waited = 0;
  var checkTimer = setInterval(async function(){
    waited += 1000;
    var healLog = 'run_heal_' + round + '.txt';
    try {
      var r = await fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({log: healLog})});
      var d = await r.json();
      if(d.ok && d.log.length > 0){
        clearInterval(checkTimer);
        setStepNum('heal', 'running');
        setLog('[힐링 ' + round + '/3] 실행 중...\n');
        _pollSingleLog(healLog, 'heal', function(ok){
          if(!ok){ _finishRunAll(false); return; }
          // heal 후 execute 재실행 결과 확인
          var exLog = 'run_execute_' + round + '.txt';
          _pollSingleLog(exLog, 'execute', function(exOk){
            if(exOk){ _finishRunAll(true); }
            else { _pollHealRounds(round + 1); }
          });
        });
      } else if(waited >= 8000){
        // 8초 내 heal이 시작 안 됐으면 서버가 이미 완료한 것으로 간주
        clearInterval(checkTimer);
        _finishRunAll(true);
      }
    } catch(_){}
  }, 1000);
}

function _pollSingleLog(logName, step, onDone){
  var prevLen = 0;
  var timer = setInterval(async function(){
    try {
      var r = await fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({log: logName})});
      var d = await r.json();
      if(d.ok && d.log.length !== prevLen){ setLog(d.log); prevLen = d.log.length; }
      if(d.done){
        clearInterval(timer);
        setStepNum(step, d.exit_code === 0 ? 'done' : 'failed');
        onDone(d.exit_code === 0);
      }
    } catch(_){}
  }, 1200);
}

function _finishRunAll(success){
  if(!_runAllHistoryRecorded){
    _runAllHistoryRecorded=true;
    fetch('/api/state').then(function(r){return r.json();}).then(function(st){
      var summary=((st||{}).execute_results||{}).summary||{};
      var total=Number(summary.total||0), passed=Number(summary.passed||0), failed=Number(summary.failed||0);
      if(!success && !total){ failed=1; total=1; }
      var rate=total?Math.round(passed/total*100):0;
      recordRunHistory({
        type:'pipeline', platform:_runAllPlatform, total:total, passed:passed, failed:failed,
        rate:rate, groups:_runAllFolders.slice(), healCount:Number((st||{}).heal_count||0),
        duration:_runAllStartedAt?Math.round((Date.now()-_runAllStartedAt)/1000)+'s':'-',
        executedAt:new Date().toISOString()
      });
    }).catch(function(){
      recordRunHistory({type:'pipeline',platform:_runAllPlatform,total:success?1:1,passed:success?1:0,failed:success?0:1,rate:success?100:0,groups:_runAllFolders.slice(),executedAt:new Date().toISOString()});
    });
  }
  _runAllActive = false;
  var btn = document.getElementById('btn-run-all');
  btn.classList.remove('loading');
  btn.disabled = false;
  _currentStep = null;
  refreshStatus(); refreshGenerated(); refreshReports();
  if(success) showGuideBanner('execute', true);
}

async function runStep(step){
  _stepStartTime = Date.now();
  hideGuideBanner();
  var platform = getPlatform();
  var btnId = 'btn-'+step;
  var cancelId = 'cancel-'+step;
  var logFiles = {
    analyze:'run_analyze.txt', generate:'run_generate.txt',
    lint:'run_lint.txt', execute:'run_execute.txt', heal:'run_heal.txt'
  };
  _currentLog = logFiles[step];
  _currentStep = step;

  // UI 업데이트
  var btn = document.getElementById(btnId);
  btn.classList.add('loading');
  btn.disabled = true;
  document.getElementById(cancelId).classList.add('visible');
  setStepNum(step,'running');
  setLog('['+step+'] 플랫폼: '+platform+' — 실행 중...\n');
  hideFails();

  try {
    var tcFolder = getTcFolder();
    var res = await fetch('/api/run',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.assign({step, platform, tc_folder: tcFolder}, getSelectedDeviceParams()))
    });
    var data = await res.json();
    if(!data.ok){
      setLog('[오류] '+(data.error||'알 수 없는 오류'));
      finishStep(step, false);
      return;
    }
    setLog('['+step+'] PID: '+data.pid+'\n');
    startLogPoll(step, _currentLog);
  } catch(e){
    setLog('[요청 실패] '+e.message);
    finishStep(step, false);
  }
}

async function cancelStep(step){
  await fetch('/api/cancel',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({step})
  });
  finishStep(step, false);
  setLog('[취소됨] '+step+' 실행이 중단됐어요.');
}

function finishStep(step, success){
  var btn=document.getElementById('btn-'+step);
  btn.classList.remove('loading');
  document.getElementById('cancel-'+step).classList.remove('visible');
  setStepNum(step, success===true?'done': success===false?'failed':'');
  if(_pollTimer){ clearInterval(_pollTimer); _pollTimer=null; }
  // Fix 5: 스텝 완료 시 _currentStep 초기화 → 이후 refreshStatus가 플랫폼 동기화 재개
  _currentStep = null;
  refreshStatus();
  refreshGenerated();
  refreshReports();

  // 소요 시간
  var elapsed = _stepStartTime ? Math.round((Date.now() - _stepStartTime) / 1000) : 0;
  // 결과 요약
  var summary = document.getElementById('step-summary');
  var summaryText = '[' + step + '] 소요 ' + elapsed + 's';
  if(step === 'execute' || step === 'heal'){
    var logText = document.getElementById('log-box').textContent;
    var passMatch = logText.match(/(\d+) passed/);
    var failMatch = logText.match(/(\d+) failed/);
    if(passMatch || failMatch){
      summaryText += ' | 통과: ' + (passMatch?passMatch[1]:'0') + ' | 실패: ' + (failMatch?failMatch[1]:'0');
    }
  }
  if(step === 'generate'){
    var logText = document.getElementById('log-box').textContent;
    var genMatch = logText.match(/(\d+)개/);
    if(genMatch) summaryText += ' | 생성: ' + genMatch[1] + '개';
  }
  summary.textContent = summaryText;
  summary.style.display = 'block';

  // 가이드 배너
  showGuideBanner(step, success === true);

  // suggested 버튼 하이라이트
  document.querySelectorAll('.btn.suggested').forEach(function(b){ b.classList.remove('suggested'); });
  if(success === true && _nextStep[step]){
    var nextBtn = document.getElementById('btn-' + _nextStep[step]);
    if(nextBtn && !nextBtn.disabled) nextBtn.classList.add('suggested');
  }
}

// ── 로그 폴링 ────────────────────────────────────────────────
function startLogPoll(step, logFile){
  if(_pollTimer) clearInterval(_pollTimer);
  var prevLen=0;
  _pollTimer = setInterval(async ()=>{
    try{
      var res=await fetch('/api/run_log',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({log:logFile})
      });
      var data=await res.json();
      if(data.ok && data.log.length!==prevLen){
        setLog(data.log);
        prevLen=data.log.length;
        // 실패 파싱
        if(step==='execute'||step==='heal'){
          updateFailSummary(data.log);
        }
      }
      if(data.done){
        clearInterval(_pollTimer);
        _pollTimer=null;
        finishStep(step, data.exit_code===0);
      }
    }catch(_){}
  }, 1200);
  // 최대 10분 타임아웃
  setTimeout(()=>{ if(_pollTimer){ clearInterval(_pollTimer); _pollTimer=null; finishStep(step,false); }}, 600000);
}

// ── 실패 요약 ────────────────────────────────────────────────
function updateFailSummary(logText){
  var lines=logText.split('\n');
  var fails=[];
  var inSummary=false;
  lines.forEach(function(l){
    if(l.includes('short test summary info')) inSummary=true;
    if(inSummary && l.startsWith('FAILED')){
      var parts=l.replace('FAILED ','').split(' - ');
      fails.push({tc:parts[0]||'', error:parts[1]||''});
    }
    // inline FAILED lines
    if(!inSummary && l.startsWith('FAILED ')){
      var parts=l.replace('FAILED ','').split(' - ');
      var entry={tc:parts[0]||'', error:parts[1]||''};
      if(!fails.some(function(f){return f.tc===entry.tc;})) fails.push(entry);
    }
  });
  if(!fails.length){ hideFails(); return; }
  var panel=document.getElementById('fail-summary');
  var list=document.getElementById('fail-list');
  document.getElementById('fail-count').textContent=fails.length;
  list.innerHTML=fails.map(function(f){
    return '<div class="fail-item"><div class="fail-tc">'+esc(f.tc)+'</div>'
      +(f.error?'<div class="fail-err">'+esc(f.error)+'</div>':'')+'</div>';
  }).join('');
  panel.classList.add('visible');
}
function hideFails(){
  document.getElementById('fail-summary').classList.remove('visible');
  document.getElementById('fail-list').innerHTML='';
}
function esc(s){ var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

function showGuideBanner(step, success){
  var banner = document.getElementById('guide-banner');
  var msgVal = (_guideMessages[step]||{})[success?'ok':'fail'];
  var msg = (msgVal === null && step === 'analyze' && !success) ? _analyzeFailMsg() : (msgVal || '');
  if(!msg){ banner.style.display='none'; return; }
  banner.style.background = success ? 'rgba(16,185,129,.12)' : 'rgba(244,63,94,.12)';
  banner.style.border = '1px solid ' + (success ? 'rgba(16,185,129,.35)' : 'rgba(244,63,94,.35)');
  banner.style.color = success ? '#10b981' : '#f43f5e';
  banner.innerHTML = msg + '<button onclick="hideGuideBanner()" style="position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;color:inherit;cursor:pointer;font-size:14px;opacity:.7">&#x2715;</button>';
  banner.style.display = 'block';
}
function hideGuideBanner(){
  document.getElementById('guide-banner').style.display='none';
}

// ── 탭 ──────────────────────────────────────────────────────
function switchTab(group, key, el){
  var prefix = group+'-';
  document.querySelectorAll('[id^="'+prefix+'"]').forEach(function(c){c.classList.remove('active');});
  document.getElementById(prefix+key).classList.add('active');
  el.closest('.card').querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  el.classList.add('active');
}

function switchGuide(key, el){
  document.querySelectorAll('.guide-panel').forEach(function(p){p.classList.remove('active');});
  document.getElementById('guide-'+key).classList.add('active');
  el.closest('.card').querySelectorAll('.guide-tab').forEach(function(t){t.classList.remove('active');});
  el.classList.add('active');
}


// ── API 새로고침 ─────────────────────────────────────────────
async function refreshStatus(){
  try{
    var platform = document.body.classList.contains('quick-mode') ? _quickPlatform : getPlatform();
    updateAutomationStatus(platform);
    var [sr,stR]=await Promise.all([
      fetch('/api/status?platform=' + platform),
      fetch('/api/state')
    ]);
    var st=await sr.json(), state=await stR.json();

    var dA=document.getElementById('dot-appium'), tA=document.getElementById('txt-appium');
    dA.className='dot '+(st.appium?'on':'off');
    tA.textContent=st.appium?'Appium 연결됨':'Appium 미기동';

    var dD=document.getElementById('dot-device'), tD=document.getElementById('txt-device');
    var isIos = (platform === 'ios');
    var noDevTxt = '디바이스 없음';
    if(st.device_count>0){ dD.className='dot on'; tD.textContent=st.devices.join(', '); }
    else{ dD.className='dot off'; tD.textContent=noDevTxt; }

    document.getElementById('txt-step').textContent=state.step||'init';

    var hc=state.heal_count||0;
    var hr=document.getElementById('heal-row');
    if(hc>0){
      hr.style.display='flex';
      document.getElementById('heal-cnt').textContent=hc;
    }else{
      hr.style.display='none';
      document.getElementById('heal-cnt').textContent='';
    }

    // Capture Studio 세션 상태 표시
    var captureActive = st.capture_active || false;
    // 페이지 로드 시 CS info-strip 동기화 (세션 복원 전 첫 폴링)
    if(captureActive && st.capture_platform && !_cs.sessionId){
      csInfoStripShow(st.capture_platform, st.capture_device || '', st.capture_group || '');
    } else if(!captureActive){
      csInfoStripHide();
    }
    // 파이프라인 실행 버튼 비활성화 (Capture 세션 중)
    var runBtns = document.querySelectorAll('.run-btn, [id^="btn-run"], [id^="btn-all"]');
    runBtns.forEach(function(btn){ btn.disabled = captureActive; });
    if(captureActive){
      var existingWarn = document.getElementById('capture-pipeline-warn');
      if(!existingWarn){
        var warnEl = document.createElement('div');
        warnEl.id = 'capture-pipeline-warn';
        warnEl.style.cssText='background:rgba(167,139,250,.12);border:1px solid rgba(167,139,250,.35);color:#a78bfa;padding:8px 14px;border-radius:8px;font-size:12px;margin:8px 0;';
        warnEl.textContent='⚠️ Capture Studio 세션이 실행 중입니다. 파이프라인 실행이 비활성화되었습니다.';
        var mainArea = document.querySelector('.tab-panel.active') || document.querySelector('.main-area');
        if(mainArea) mainArea.insertBefore(warnEl, mainArea.firstChild);
      }
    } else {
      var existingWarn = document.getElementById('capture-pipeline-warn');
      if(existingWarn) existingWarn.remove();

      // ── 30분 세션 만료 감지 ──
      // Capture 워크스페이스가 열려 있는데 서버가 capture_active=false로 바꿨으면 만료
      var _workspace = document.getElementById('cs-workspace');
      if(_cs.sessionId && _workspace && _workspace.style.display !== 'none') {
        var _expiredBanner = document.getElementById('cs-expired-banner');
        if(!_expiredBanner){
          var _banner = document.createElement('div');
          _banner.id = 'cs-expired-banner';
          _banner.style.cssText = 'background:rgba(251,113,133,.1);border:1px solid rgba(251,113,133,.4);color:#fb7185;' +
            'padding:10px 16px;border-radius:8px;font-size:12px;margin-bottom:10px;display:flex;align-items:center;gap:10px;';
          _banner.innerHTML = '⏰ Capture 세션이 30분 비활동으로 자동 종료됐습니다. 기록은 보존됩니다.' +
            '<button class="cs-btn" onclick="csForceNewSession()" style="padding:3px 10px;font-size:11px;flex-shrink:0">새 세션 시작</button>' +
            '<button class="cs-btn" onclick="csReLaunch()" style="padding:3px 10px;font-size:11px;flex-shrink:0">🔄 재연결</button>';
          _workspace.insertBefore(_banner, _workspace.firstChild);
        }
      }
    }

    // 최초 로드 시 pipeline.json 플랫폼으로 라디오 동기화
    if(state.platform && _initialPlatformSync){
      var r=document.getElementById('radio-'+state.platform);
      var changed = r && !r.checked;
      if(r) r.checked=true;
      _initialPlatformSync = false;
      updateAutomationStatus(state.platform);
      if(changed) setTimeout(refreshStatus, 0);
    }
  }catch(_){}
}

function updateAutomationStatus(platform){
  var el=document.getElementById('txt-automation');
  if(!el) return;
  if(platform === 'ios'){
    el.textContent='자동화: XCUITest';
    el.title='iOS · XCUITest · Simulator / 실기기';
  }else{
    el.textContent='자동화: ADB';
    el.title='Android · ADB · UiAutomator2';
  }
}

// 라디오 버튼 변경 시 즉시 상태 갱신
document.addEventListener('change', function(e){
  if(e.target && e.target.name === 'platform'){
    updateAutomationStatus(e.target.value);
    refreshStatus();
    refreshTcFolders();
  }
});

// ── TC 폴더 목록 ─────────────────────────────────────────────
async function refreshTcFolders(){
  try{
    var res = await fetch('/api/tc-folders?platform='+encodeURIComponent(getPlatform()));
    var data = await res.json();
    var list = document.getElementById('tc-folder-list');
    if(!list) return;
    var selected = getTcFolders();
    var folders = data.folders||[];
    list.innerHTML = folders.length ? folders.map(function(f){
      var checked = selected.length ? selected.indexOf(f)!==-1 : true;
      return '<label class="tc-folder-option"><input type="checkbox" name="tc-folder" value="'+esc(f)+'" '+(checked?'checked':'')+' onchange="updateTcFolderCount()"><span>'+esc(f)+'/</span></label>';
    }).join('') : '<div class="tc-folder-empty">생성된 TC 폴더가 없습니다.</div>';
    updateTcFolderCount();
  }catch(_){}
}
