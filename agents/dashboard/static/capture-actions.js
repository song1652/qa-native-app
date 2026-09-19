function csToggleRecord() {
  _cs.recording = !_cs.recording;
  var btn = document.getElementById('cs-record-btn');
  btn.textContent = _cs.recording ? '⏸ 일시정지' : '● 녹화 시작';
  btn.style.color = _cs.recording ? '#f87171' : '';
  btn.style.borderColor = _cs.recording ? 'rgba(248,113,113,.4)' : '';
}

function csSendBack() {
  fetch('/capture/back', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: _cs.sessionId, context: _cs.context})
  }).then(function(r){ return r.json(); }).then(function(d){
    if (!d.ok) csStatusMsg('Back 실패: ' + (d.error||''));
  }).catch(function(err){ csStatusMsg('Back 오류: ' + err); });
}

function csClearActions() {
  if(!confirm('Action Timeline을 초기화하시겠습니까?')) return;
  _cs.actions = [];
  csRenderTimeline();
  // 서버 session["actions"]와 actions.json도 동기화
  var sid = _cs.sessionId;
  if (sid) {
    fetch('/capture/clear_actions', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({session_id: sid})
    }).then(function(r){ return r.json(); }).then(function(d){
      if (!d.ok) csStatusMsg('⚠️ 서버 초기화 실패: ' + (d.error || ''));
    }).catch(function(e){ csStatusMsg('⚠️ 서버 동기화 오류: ' + e); });
  }
}

// 요소 선택 없이 바로 추가하는 직접 스텝
function csAddDirectStep(type) {
  var step;
  if (type === 'back') {
    step = { type: 'back', label: 'Back 버튼', step: 'Back 버튼을 누른다', expected: '' };
    _cs.actions.push(step);
    csRenderTimeline();
    csStatusMsg(step.label + ' 스텝이 추가되었습니다.');
    // 실제 Back 실행 (비동기) → 완료 후 hierarchy 자동 새로고침
    var sid = _cs.sessionId;
    if(sid) fetch('/capture/back', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:sid})
    }).then(function(){ setTimeout(function(){ csRefreshHierarchy(); }, 1200); })
      .catch(function(){});
  } else if (type === 'scroll_down' || type === 'scroll_up') {
    var dir = (type === 'scroll_up') ? 'up' : 'down';
    var label = dir === 'up' ? '위로 스크롤' : '아래로 스크롤';
    step = { type: type, label: label,
             step: '화면을 ' + (dir === 'up' ? '위' : '아래') + '로 스크롤한다', expected: '' };
    _cs.actions.push(step);
    csRenderTimeline();
    csStatusMsg(label + ' — 디바이스 스크롤 중...');

    // 실제 디바이스 스크롤 실행 → 완료 후 hierarchy 자동 새로고침
    var sid2 = _cs.sessionId;
    if(sid2) {
      fetch('/capture/scroll', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({session_id:sid2, direction:dir})
      }).then(function(r){ return r.json(); }).then(function(d){
        if(d.ok){
          csStatusMsg(label + ' 완료 — Hierarchy 새로고침 중...');
          // 잠시 후 자동 새로고침
          setTimeout(function(){ csRefreshHierarchy(); }, 800);
        } else {
          csStatusMsg('⚠️ 스크롤 실패: ' + (d.error||''));
        }
      }).catch(function(e){ csStatusMsg('⚠️ 스크롤 오류: ' + e); });
    } else {
      csStatusMsg('⚠️ 세션 없음 — 스텝만 추가됨');
    }
  } else if (type === 'wait') {
    var sec = prompt('대기 시간 (초, 숫자):', '1');
    if (!sec) return;
    var secNum = parseFloat(sec);
    if (isNaN(secNum) || secNum <= 0) { alert('올바른 숫자를 입력하세요 (예: 1, 2.5)'); return; }
    secNum = Math.min(secNum, 60); // 최대 60초
    step = { action: 'wait', type: 'wait', wait_seconds: secNum,
             label: secNum + '초 대기', step: secNum + '초 대기한다', expected: '' };
    _cs.actions.push(step);
    csRenderTimeline();
    csStatusMsg(step.label + ' 스텝이 추가되었습니다.');
  }
}

var _CS_ACTION_ICONS = {tap:'👆',input:'⌨️',back:'⬅️',scroll_down:'↓',scroll_up:'↑',wait:'⏱',context_switch:'🔄',assertion:'✅'};

function csActionStepText(a) {
  // Human-readable step draft (Phase 5)
  switch(a.action) {
    case 'tap':
      if (a.target_ref) return '"' + a.target_ref + '" 탭';
      if (a.device_x !== undefined) return '좌표 (' + a.device_x + ', ' + a.device_y + ') 탭';
      return '화면 탭';
    case 'input':
      var val = a.is_secret ? '***' : ('"' + (a.value||'') + '"');
      if (a.target_ref) return '"' + a.target_ref + '"에 ' + val + ' 입력';
      return val + ' 입력';
    case 'back':
      return '뒤로가기 (Back)';
    case 'context_switch':
      return (a.to_context === 'webview' ? 'WebView 전환' : 'Native 전환');
    case 'assertion':
      var aLabel = a.label || a.value || a.description || a.target_ref || '';
      if (a.assertion_type === 'text_visible') return aLabel + ' 텍스트 확인: "' + (a.assertion_value || '') + '"';
      if (a.assertion_type === 'element_present') return aLabel + ' 요소 존재 확인';
      if (a.assertion_type === 'element_absent') return aLabel + ' 요소 없음 확인';
      return '검증: ' + (a.description || a.target_ref || aLabel);
    default:
      return a.action + (a.target_ref ? ' → ' + a.target_ref : '');
  }
}

function csRenderTimeline() {
  var el = document.getElementById('cs-timeline');
  if (!_cs.actions.length) {
    el.innerHTML = '<span id="cs-timeline-empty" style="color:var(--text3)">트리에서 요소를 선택하고 스텝을 추가하세요.</span>';
    return;
  }
  el.innerHTML = _cs.actions.map(function(a, i){
    var icon = _CS_ACTION_ICONS[a.action] || '·';
    var stepText = csActionStepText(a);
    var expectedVal = esc(a.expected || '');
    return '<div class="cs-action-row" style="flex-direction:column;align-items:stretch">'
      + '<div style="display:flex;align-items:center;gap:8px">'
      + '<span class="cs-action-idx">' + a.index + '</span>'
      + '<span class="cs-action-icon">' + icon + '</span>'
      + '<span class="cs-action-body">' + esc(stepText) + '</span>'
      + '<span class="cs-action-ctx" style="font-size:9px">' + esc(a.context||'') + '</span>'
      + '</div>'
      + '<textarea data-action-idx="' + i + '" placeholder="기대 결과 입력 (선택)"'
      + ' style="margin-top:4px;margin-left:44px;width:calc(100% - 48px);height:36px;resize:none;font-size:10px;'
      + 'padding:4px 6px;border-radius:4px;border:1px solid var(--border);background:rgba(255,255,255,.04);'
      + 'color:var(--text);outline:none;transition:height .15s;box-sizing:border-box"'
      + ' oninput="csSetStepExpected(' + i + ',this.value)"'
      + ' onfocus="this.style.height=\'60px\'" onblur="if(!this.value)this.style.height=\'36px\'">'
      + expectedVal + '</textarea>'
      + '</div>';
  }).join('');
}

function csSetStepExpected(idx, value) {
  if (_cs.actions[idx] !== undefined) {
    _cs.actions[idx].expected = value;
  }
}

function csPreviewTC() {
  var tcId = document.getElementById('cs-tc-id').value.trim() || 'tc_preview';
  var title = document.getElementById('cs-tc-title').value.trim() || '(제목 없음)';
  var platform = document.getElementById('cs-platform').value || 'android';
  var group = document.getElementById('cs-group').value.trim() || 'default';
  var steps = _cs.actions.map(function(a, i){ return (i+1) + '. ' + csActionStepText(a); });
  var expected = _cs.actions.map(function(){ return ''; });

  // Markdown
  var md = '# ' + tcId + ': ' + title + '\n\n'
    + '## 플랫폼\n\n' + platform.charAt(0).toUpperCase() + platform.slice(1) + '\n\n'
    + '## 사전 조건\n\n앱 실행 및 초기 화면 진입\n\n'
    + '## 단계\n\n' + steps.join('\n') + '\n\n'
    + '## 기대결과\n\n_(기대 결과를 입력하세요)_\n\n'
    + '## 태그\n\ncapture-studio';

  // pytest 초안 — 실제 generate_from_actions 출력 형식(클래스 기반)과 동일한 구조로 표시
  var snakeId = tcId.replace(/-/g, '_').replace(/[^a-zA-Z0-9_]/g, '_');
  var className = 'Test' + snakeId.split('_').map(function(w){ return w.charAt(0).toUpperCase()+w.slice(1); }).join('');
  var pyLines = [
    '# ⚠️ 이 코드는 미리보기 초안입니다. 저장 후 실제 생성 코드를 확인하세요.',
    '# Auto-generated by Capture Studio',
    '# TC: ' + tcId + ' — ' + title,
    '',
    'from appium.webdriver.common.appiumby import AppiumBy',
    '',
    '',
    'def _build_driver(): ...',
    '',
    '',
    'class ' + className + ':',
    '    def setup_method(self):',
    '        self.driver = _build_driver()',
    '',
    '    def test_' + snakeId + '(self):',
    '        """' + title + '"""',
  ];
  _cs.actions.forEach(function(a, i) {
    pyLines.push('        # Step ' + (i+1) + ': ' + csActionStepText(a));
    if (a.action === 'tap') {
      if (a.locator_strategy && a.locator_value) {
        pyLines.push('        self.driver.find_element(AppiumBy.' + a.locator_strategy.toUpperCase().replace(/-/g,'_') + ', "' + a.locator_value + '").click()');
      } else if (a.device_x !== undefined) {
        pyLines.push('        self.driver.tap([(' + a.device_x + ', ' + a.device_y + ')])');
      }
    } else if (a.action === 'input') {
      pyLines.push('        # self.driver.find_element(...).send_keys("' + (a.is_secret ? '***' : (a.value||'')) + '")');
    } else if (a.action === 'back') {
      pyLines.push('        self.driver.back()');
    } else if (a.action === 'scroll_down') {
      pyLines.push('        # scroll down');
    } else if (a.action === 'scroll_up') {
      pyLines.push('        # scroll up');
    } else if (a.action === 'wait') {
      pyLines.push('        import time; time.sleep(' + (a.wait_seconds || 1) + ')');
    }
  });
  pyLines.push('        # assert ...');

  document.getElementById('cs-preview-md').textContent = md;
  document.getElementById('cs-preview-py').textContent = pyLines.join('\n');
  var modal = document.getElementById('cs-preview-modal');
  modal.style.display = 'flex';
}

function csClosePreview() {
  document.getElementById('cs-preview-modal').style.display = 'none';
}

function csSaveTC() {
  var tcId = document.getElementById('cs-tc-id').value.trim();
  var title = document.getElementById('cs-tc-title').value.trim();
  if(!tcId || !title){ alert('TC ID와 제목을 입력하세요.'); return; }
  if(!_cs.actions.length){ alert('기록된 Action이 없습니다.'); return; }

  var steps = _cs.actions.map(function(a){ return csActionStepText(a); });
  var expected = _cs.actions.map(function(a){ return a.expected || ''; });
  var platform = document.getElementById('cs-platform').value;

  // approvedLocators 배열을 서버가 기대하는 dict 형식으로 변환
  var approvedDict = {};
  _cs.approvedLocators.forEach(function(l) {
    var key = tcId + '.' + l.strategy.replace(/-/g, '_');
    approvedDict[key] = { strategy: l.strategy, value: l.value, confidence: l.rating / 5 };
  });

  document.getElementById('cs-save-btn').disabled = true;
  document.getElementById('cs-save-status').textContent = '저장 중...';

  fetch('/capture/save', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      session_id: _cs.sessionId,
      tc_id: tcId,
      title: title,
      platform: platform,
      tc_group: document.getElementById('cs-group').value.trim() || 'default',
      steps: steps,
      expected: expected,
      approved_locators: approvedDict,
      overwrite: true,
    })
  }).then(function(r){ return r.json(); }).then(function(d){
    document.getElementById('cs-save-btn').disabled = false;
    if(d.ok){
      var msg = '✅ TC 저장 완료 — 테스트 코드 생성 중…';
      if(d.quality_tag) msg += ' ⚠️ 기대 결과 누락';
      var statusEl = document.getElementById('cs-save-status');
      statusEl.textContent = msg;
      statusEl.style.color = 'var(--text3)';
      // TC 저장 후 자동으로 테스트 코드 생성
      csAutoGenerate(platform, d.tc_file);
    } else {
      document.getElementById('cs-save-status').textContent = '❌ ' + (d.error||'저장 실패');
      document.getElementById('cs-save-status').style.color = 'var(--fail)';
    }
  }).catch(function(err){
    document.getElementById('cs-save-btn').disabled = false;
    document.getElementById('cs-save-status').textContent = '❌ 오류: ' + err;
    document.getElementById('cs-save-status').style.color = 'var(--fail)';
  });
}

function csShowGenerateBtn(platform) {} // 자동 생성으로 대체 — 수동 버튼 불필요

// _cs.actions를 서버 코드 생성 포맷으로 변환
function _csActionsForCodeGen() {
  return _cs.actions.map(function(a) {
    return {
      type: a.action || a.type || '',
      label: a.label || a.target_ref || '',
      locator_strategy: a.strategy || '',   // csAddStep에서 저장한 strategy
      locator_value:    a.value   || '',    // csAddStep에서 저장한 locator value
      assertion_type:   a.assertion_type  || '',
      assertion_value:  a.assertion_value || '',
      input_value:      a.input_text      || '',
      wait_seconds:     a.wait_seconds    || 1,
      device_x:         a.device_x,
      device_y:         a.device_y,
    };
  });
}

// TC 저장 직후 자동으로 테스트 코드 생성 + 결과 패널 표시
function csAutoGenerate(platform, tcFile) {
  var tcId = document.getElementById('cs-tc-id').value.trim() || 'tc_generated';
  var title = document.getElementById('cs-tc-title').value.trim() || 'TC';
  var group = document.getElementById('cs-group').value.trim() || 'default';
  fetch('/capture/generate_from_actions', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      session_id: _cs.sessionId,
      tc_id: tcId, title: title, platform: platform, tc_group: group,
      actions: _csActionsForCodeGen(),
    })
  }).then(function(r){ return r.json(); }).then(function(d){
    var statusEl = document.getElementById('cs-save-status');
    // generate_from_actions 응답: {ok, file, code, lines} (returncode 없음)
    if (d.ok) {
      statusEl.textContent = '✅ 테스트 코드 생성 완료 → ' + (d.file || d.generated_file || ('tests/generated/' + platform));
      statusEl.style.color = 'var(--pass)';
      // 생성된 코드 패널 표시
      csShowGeneratedCode(platform, d);
    } else {
      statusEl.textContent = '⚠️ TC 저장됨, 코드 생성 실패: ' + (d.error || '알 수 없는 오류');
      statusEl.style.color = 'var(--warn)';
    }
  }).catch(function(err){
    document.getElementById('cs-save-status').textContent = '⚠️ TC 저장됨, 코드 생성 오류: ' + err;
    document.getElementById('cs-save-status').style.color = 'var(--warn)';
  });
}

// 생성된 Python 테스트 코드를 코드 뷰어 패널에 표시
function csShowGeneratedCode(platform, genResult) {
  var existing = document.getElementById('cs-code-panel');
  if (existing) existing.remove();

  var code = genResult.output || genResult.code || '';
  // generate_from_actions 응답 필드: file (generated_file은 구버전)
  var filePath = genResult.file || genResult.generated_file || '';

  var panel = document.createElement('div');
  panel.id = 'cs-code-panel';
  panel.style.cssText = 'margin-top:14px;border:1px solid rgba(96,165,250,.35);border-radius:10px;overflow:hidden';
  panel.innerHTML = '<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:rgba(96,165,250,.08);border-bottom:1px solid rgba(96,165,250,.2)">'
    + '<span style="font-size:12px;font-weight:600;color:#60a5fa">🐍 생성된 테스트 코드 (' + platform + ')</span>'
    + '<button class="cs-btn" onclick="csLoadGeneratedFile(\'' + platform + '\')" style="padding:3px 10px;font-size:10px">↻ 새로고침</button>'
    + '</div>'
    + '<pre id="cs-code-body" style="margin:0;padding:14px;overflow-x:auto;font:12px/1.6 monospace;color:var(--text2);background:rgba(8,7,27,.4);max-height:420px;overflow-y:auto">'
    + (code ? esc(code.slice(0,4000)) : '코드를 불러오는 중…')
    + '</pre>';

  var timeline = document.getElementById('cs-timeline');
  if (timeline && timeline.parentNode) {
    timeline.parentNode.parentNode.appendChild(panel);
  }

  // 생성된 파일 내용 직접 로드
  csLoadGeneratedFile(platform);
}

function csLoadGeneratedFile(platform) {
  fetch('/capture/generated_code?platform=' + platform)
    .then(function(r){ return r.json(); })
    .then(function(d){
      var el = document.getElementById('cs-code-body');
      if (el && d.code) el.textContent = d.code;
      else if (el && d.error) el.textContent = '// ' + d.error;
    }).catch(function(){});
}

function csRunGenerate(platform, btn) { csAutoGenerate(platform); }

// 드라이버 죽음 상태에서 setup 화면에서 재실행
function csReLaunchFromSetup() {
  var statusEl = document.getElementById('cs-setup-status');
  if(_cs.launching){
    if(statusEl){ statusEl.textContent = '📱 앱 실행이 이미 진행 중입니다. 잠시 기다려 주세요.'; statusEl.style.color='#a78bfa'; }
    return;
  }
  _cs.launching = true;
  var _rfsIsIos = (_cs.screenshotMode === 'poll');
  var _rfsTimeout = _rfsIsIos ? 180000 : 45000;
  var _rfsStartTs = Date.now();
  if(statusEl){ statusEl.textContent = '📱 앱 재실행 중...'; statusEl.style.color='#a78bfa'; }
  var _rfsProgress = setInterval(function(){
    var s = Math.round((Date.now() - _rfsStartTs) / 1000);
    if(statusEl) statusEl.textContent = '📱 앱 재실행 중… (' + s + '초 경과' + (_rfsIsIos ? ' / 최대 180초' : '') + ')';
  }, 2000);
  var _ctrl = new AbortController();
  var _ctrlTimer = setTimeout(function(){ _ctrl.abort(); }, _rfsTimeout);
  fetch('/capture/launch', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: _cs.sessionId}),
    signal: _ctrl.signal
  }).then(function(r){ clearTimeout(_ctrlTimer); clearInterval(_rfsProgress); return r.json(); }).then(function(d){
    _cs.launching = false;
    if(d.ok){
      document.getElementById('cs-setup').style.display='none';
      document.getElementById('cs-workspace').style.display='block'; setTimeout(function(){ csStartMirrorObserver(); csSyncPanelHeight(); }, 100);
      document.getElementById('cs-session-badge').style.display='';
      csRenderTimeline();
      csMirrorConnect();
      setTimeout(function(){ csRefreshHierarchy(); }, 1500);
      var saveStatus = document.getElementById('cs-save-status');
      if(saveStatus){ saveStatus.textContent = '✅ 앱 재실행됨'; saveStatus.style.color='var(--pass)'; }
    } else {
      if(statusEl){ statusEl.textContent = '❌ 재실행 실패: ' + (d.error||'알 수 없는 오류'); statusEl.style.color='var(--fail)'; }
    }
  }).catch(function(err){
    _cs.launching = false;
    clearTimeout(_ctrlTimer); clearInterval(_rfsProgress);
    var s2 = Math.round((Date.now() - _rfsStartTs) / 1000);
    var msg = err && err.name==='AbortError'
      ? '⏱ ' + s2 + '초 초과 — Appium/디바이스 상태를 확인하세요'
      : '❌ 오류: ' + err;
    if(statusEl){ statusEl.textContent = msg; statusEl.style.color='var(--fail)'; }
  });
}

// 이전 세션 버리고 새 세션 시작
function csForceNewSession() {
  fetch('/capture/end', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: _cs.sessionId})
  }).catch(function(){}).finally(function(){
    if(_cs.pollTimer){ clearInterval(_cs.pollTimer); _cs.pollTimer = null; }
    csStopScreenWatcher();
    csMcpStopPoll();
    _cs.sessionId = '';
    _cs.actions = [];
    _cs.recording = false;
    _cs.approvedLocators = [];
    _cs.screenshotMode = 'mjpeg';
    if(_csLtOpen) csToggleLivetail();
    document.getElementById('cs-setup').style.display='block';
    document.getElementById('cs-workspace').style.display='none';
    document.getElementById('cs-session-badge').style.display='none';
    csInfoStripHide();
    document.getElementById('cs-start-btn').disabled = false;
    var statusEl = document.getElementById('cs-setup-status');
    if(statusEl){ statusEl.textContent = '새 세션을 시작할 수 있습니다.'; statusEl.style.color='var(--text3)'; }
  });
}

function csEndSession() {
  if(!confirm('Capture 세션을 종료하시겠습니까? 저장하지 않은 기록은 유실됩니다.')) return;
  fetch('/capture/end', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: _cs.sessionId})
  }).then(function(r){ return r.json(); }).then(function(d){
    if(_cs.pollTimer){ clearInterval(_cs.pollTimer); _cs.pollTimer = null; }
    csStopScreenWatcher();
    csMcpStopPoll();
    _cs.sessionId = '';
    _cs.actions = [];
    _cs.recording = false;
    _cs.screenshotMode = 'mjpeg';
    if(_csLtOpen) csToggleLivetail();
    document.getElementById('cs-setup').style.display='block';
    document.getElementById('cs-workspace').style.display='none';
    document.getElementById('cs-session-badge').style.display='none';
    csInfoStripHide();
    document.getElementById('cs-start-btn').disabled = false;
    document.getElementById('cs-setup-status').textContent = '세션이 종료되었습니다.';
  });
}

function csStatusMsg(msg) {
  var el = document.getElementById('cs-save-status');
  if(el){ el.textContent = msg; }
}

// ── Healing 재확인: Locator 검토 재진입 ──────────────────────
async function csOpenHealReview(platform, testFile) {
  // 1. Capture Studio 탭으로 이동
  var captureItem = document.querySelector('.sidebar-item[data-view=capture]');
  selectView('capture', captureItem);
  if(!_csInitialized){ _csInitialized=true; await csInit(); }

  // 2. 재확인 모드 표시
  var badge = document.getElementById('cs-session-badge');
  if(badge){ badge.textContent='🔍 Locator 재확인 모드'; badge.style.display=''; }

  // 3. 해당 TC의 actions.json 로드 시도
  //    파일명에서 TC 슬러그 추출: tests/generated/android/settings/tc_001_xxx.py
  var tcFile = testFile.replace(/^.*\//, '').replace(/\.py$/, '') + '.md';
  var folder = testFile.includes('/') ? testFile.split('/').slice(0,-1).join('/') : '';

  // 4. 워크스페이스 표시 (세션 없어도 재확인 모드 진입)
  document.getElementById('cs-setup').style.display='none';
  document.getElementById('cs-workspace').style.display='block'; setTimeout(function(){ csStartMirrorObserver(); csSyncPanelHeight(); }, 100);
  // 활성 세션이 있으면 미러링 자동 시작
  if(_cs.sessionId) { setTimeout(function(){ csMirrorConnect(); csRefreshHierarchy(); }, 500); }

  // 5. 재확인 안내 메시지
  var saveStatus = document.getElementById('cs-save-status');
  if(saveStatus){
    saveStatus.textContent = '🔍 재확인 모드: ' + testFile + ' — 실패한 Locator를 선택하고 승인하세요.';
    saveStatus.style.color = '#a78bfa';
  }

  // 6. 4단계 Locator 검토 패널 강조
  var locatorsEl = document.getElementById('cs-locators');
  if(locatorsEl){
    locatorsEl.innerHTML = '<div style="color:#a78bfa;font-weight:600;margin-bottom:8px">🔍 Healing 재확인</div>'
      + '<div style="color:var(--text2);font-size:11px">파일: ' + esc(testFile) + '</div>'
      + '<div style="color:var(--text3);font-size:11px;margin-top:6px">Appium 세션을 시작하고 실패 화면으로 이동한 뒤<br>요소를 선택하면 Locator 후보가 여기에 표시됩니다.</div>';
  }

  // 7. TC 정보 미리 채우기
  var tcIdEl = document.getElementById('cs-tc-id');
  var titleEl = document.getElementById('cs-tc-title');
  if(tcIdEl) tcIdEl.value = testFile.replace(/^.*\//, '').replace(/\.py$/, '');
  if(titleEl) titleEl.value = platform + ' / ' + testFile.replace(/^.*\//, '');
}

// Capture Studio 탭 선택 시 초기화
var _csInitialized = false;
var _origSelectView = typeof selectView === 'function' ? selectView : null;
// selectView 함수 후킹 (Capture 탭 선택 감지)
document.addEventListener('DOMContentLoaded', function(){
  var captureItem = document.getElementById('sidebar-capture');
  if(captureItem){
    captureItem.addEventListener('click', function(){
      if(!_csInitialized){ _csInitialized=true; csInit(); }
    });
  }
  csConnectWsTimeline();
});

// ── Livetail 슬라이드 오버레이 ──────────────────────────
var _csLtOpen = false;
var _csLtRows = [];
var _csLtFilters = {user:true, mcp:true, pipe:true};
var _csLtPinned = true;

// ── MCP 상태 폴링 ────────────────────────────────────────
var _csMcpPollTimer = null;
