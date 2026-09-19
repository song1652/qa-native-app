function csMcpStatusPoll() {
  fetch('/mcp/status').then(function(r){ return r.json(); }).then(function(d){
    csInfoStripMcp(d.connected);
  }).catch(function(){});
}

function csMcpStartPoll() {
  if(_csMcpPollTimer) return;
  csMcpStatusPoll();
  _csMcpPollTimer = setInterval(csMcpStatusPoll, 3000);
}

function csMcpStopPoll() {
  if(_csMcpPollTimer){ clearInterval(_csMcpPollTimer); _csMcpPollTimer = null; }
  csInfoStripMcp(false);
}

// ── CS 미러링 연결 상태 칩 ──────────────────────────────────
function csSubStatusConn(connected) {
  var dot = document.getElementById('cs-info-conn-dot');
  var txt = document.getElementById('cs-info-conn-label');
  if(dot){ dot.style.background = connected ? 'var(--pass)' : 'var(--fail)'; dot.className = ''; }
  if(txt){ txt.textContent = connected ? '연결됨' : '미러링 끊김'; txt.style.color = connected ? 'var(--pass)' : 'var(--fail)'; }
}
function csSubStatusUpdate(platform, deviceName) { /* no-op: csInfoStripShow handles this */ }
function csSubStatusHide() { /* no-op: csInfoStripHide handles this */ }

// ── CS 세션 정보 스트립 ───────────────────────────────────────
function csInfoStripShow(platform, deviceName, group) {
  var strip = document.getElementById('cs-info-strip');
  if (!strip) return;
  // 디바이스 칩 — Android 세션에 iOS device_name이 잔존하면 ADB 디바이스로 대체
  var isIos = (platform === 'ios');
  var platLabel = isIos ? 'iOS' : 'Android';
  var resolvedDevice = deviceName || '';
  if (!isIos && resolvedDevice && /iphone|simulator/i.test(resolvedDevice)) {
    // stale iOS device_name → 현재 ADB 연결 디바이스로 대체
    var adbEl = document.getElementById('txt-device');
    resolvedDevice = (adbEl && adbEl.textContent && adbEl.textContent !== '없음') ? adbEl.textContent : 'emulator';
  }
  var devText = resolvedDevice ? platLabel + ' \xb7 ' + resolvedDevice : platLabel;
  document.getElementById('cs-info-device-label').textContent = devText;
  // 그룹 칩
  document.getElementById('cs-info-group-label').textContent = group || 'default';
  // MCP 칩
  csInfoStripMcp(false);
  strip.classList.add('visible');
  // 연결 상태 초기화
  csSubStatusConn(false);
}

function csInfoStripHide() {
  var strip = document.getElementById('cs-info-strip');
  if (strip) strip.classList.remove('visible');
}

function csInfoStripMcp(on) {
  var chip = document.getElementById('cs-info-mcp');
  var dot  = document.getElementById('cs-info-mcp-dot');
  var label = document.getElementById('cs-info-mcp-label');
  if (!chip) return;
  if (on) {
    chip.className = 'cs-info-chip mcp-on';
    dot.className  = 'cs-info-dot green';
    label.textContent = 'MCP ON';
  } else {
    chip.className = 'cs-info-chip mcp-off';
    dot.className  = 'cs-info-dot gray';
    label.textContent = 'MCP OFF';
  }
}

var _csMcpTooltipTimer = null;
function csMcpChipClick() {
  var chip = document.getElementById('cs-info-mcp');
  if (!chip) return;
  if (chip.classList.contains('mcp-on')) {
    // ON → 해제 확인 후 disconnect
    if (!confirm('MCP 연결을 해제할까요?\nClaude Code에서 다시 도구를 호출하면 자동으로 재연결됩니다.')) return;
    fetch('/mcp/session', {method: 'DELETE'}).then(function(r){ return r.json(); }).then(function(d){
      if (d.ok) csInfoStripMcp(false);
    }).catch(function(){});
  } else {
    // OFF → 툴팁 2초 표시
    var tip = document.getElementById('cs-mcp-tooltip');
    if (!tip) return;
    tip.classList.add('visible');
    if (_csMcpTooltipTimer) clearTimeout(_csMcpTooltipTimer);
    _csMcpTooltipTimer = setTimeout(function(){ tip.classList.remove('visible'); }, 2500);
  }
}

function csToggleLivetail() {
  _csLtOpen = !_csLtOpen;
  var overlay = document.getElementById('csLtOverlay');
  var btn     = document.getElementById('csLivetailBtn');
  var label   = document.getElementById('csLtBtnLabel');
  if (_csLtOpen) {
    overlay.classList.add('open');
    btn.classList.add('lt-active');
    label.textContent = 'Livetail ✕';
    csLtRender();
    csLtScrollBottom();
  } else {
    overlay.classList.remove('open');
    btn.classList.remove('lt-active');
    label.textContent = 'Livetail';
  }
}

function csLtAppend(source, type, platform, summary, result, ms) {
  var now = new Date();
  var ts = now.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  var icon = source === 'user' ? '\u{1F464}' : source === 'mcp' ? '\u{1F916}' : '⚙';
  var row = {ts:ts, source:source, icon:icon, type:type, platform:platform, summary:summary, result:result, ms:ms};
  _csLtRows.push(row);
  if (_csLtRows.length > 200) _csLtRows.shift();
  if (_csLtOpen) {
    csLtRenderRow(row);
    if (_csLtPinned) csLtScrollBottom();
  }
}

function csLtRenderRow(row) {
  var container = document.getElementById('csLtRows');
  if (!container) return;
  var cat = row.source === 'pipeline' ? 'pipe' : row.source;
  if (!_csLtFilters[cat]) return;
  var div = document.createElement('div');
  div.className = 'lt-ov-row' + (row.source === 'pipeline' ? ' lt-pipe' : '');
  var resClass = row.result === 'ok' ? 'ok' : row.result === 'warn' ? 'wn' : 'fl';
  var resIcon  = row.result === 'ok' ? '✅' : row.result === 'warn' ? '⚠' : '❌';
  var msStr    = row.ms ? ' ' + row.ms : '';
  div.innerHTML =
    '<div class="lt-ov-t">' + row.ts + '</div>' +
    '<div class="lt-ov-ic">' + row.icon + '</div>' +
    '<div class="lt-ov-b"><span class="lt-ty">' + row.type + '</span>' +
      (row.summary ? '<span class="lt-co">' + row.summary + '</span>' : '') +
    '</div>' +
    '<div class="lt-ov-r ' + resClass + '">' + resIcon + msStr + '</div>';
  container.appendChild(div);
}

function csLtRender() {
  var container = document.getElementById('csLtRows');
  if (!container) return;
  container.innerHTML = '';
  _csLtRows.forEach(function(row){ csLtRenderRow(row); });
}

function csLtScrollBottom() {
  var container = document.getElementById('csLtRows');
  if (container) container.scrollTop = container.scrollHeight;
}

function csLtFilter(cat, el) {
  _csLtFilters[cat] = !_csLtFilters[cat];
  el.style.opacity = _csLtFilters[cat] ? '1' : '0.35';
  if (_csLtOpen) { csLtRender(); csLtScrollBottom(); }
}

function csLtExport() {
  var lines = _csLtRows.map(function(r){
    return [r.ts, r.source, r.type, r.summary||'', r.result, r.ms||''].join('\t');
  });
  var blob = new Blob([lines.join('\n')], {type:'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'livetail_' + new Date().toISOString().slice(0,19).replace(/:/g,'-') + '.txt';
  a.click();
}

document.addEventListener('DOMContentLoaded', function(){
  var rows = document.getElementById('csLtRows');
  if (rows) {
    rows.addEventListener('scroll', function(){
      var atBottom = rows.scrollHeight - rows.scrollTop - rows.clientHeight < 20;
      _csLtPinned = atBottom;
      var pin = document.getElementById('csLtPin');
      if (pin) pin.textContent = atBottom ? '⬇ 하단 고정' : '▲ 위로 스크롤 중 — 클릭하여 고정';
      if (pin) pin.style.cursor = atBottom ? 'default' : 'pointer';
      if (pin && !atBottom) pin.onclick = function(){ _csLtPinned=true; csLtScrollBottom(); };
    });
  }
});

// ── 미러 스와이프 감지 ──────────────────────────────────
var _csSwipe = {active:false, startX:0, startY:0, curX:0, curY:0};

function csMirrorMouseDown(e) {
  e.preventDefault();
  var rect = e.currentTarget.getBoundingClientRect();
  _csSwipe.active = true;
  _csSwipe.startX = e.clientX - rect.left;
  _csSwipe.startY = e.clientY - rect.top;
  _csSwipe.curX   = _csSwipe.startX;
  _csSwipe.curY   = _csSwipe.startY;
  _csSwipeRemoveArrow();
}

function csMirrorMouseMove(e) {
  if (!_csSwipe.active) return;
  var rect = e.currentTarget.getBoundingClientRect();
  _csSwipe.curX = e.clientX - rect.left;
  _csSwipe.curY = e.clientY - rect.top;
  var dx = _csSwipe.curX - _csSwipe.startX;
  var dy = _csSwipe.curY - _csSwipe.startY;
  if (Math.sqrt(dx*dx+dy*dy) >= 10) {
    _csSwipeDrawArrow(e.currentTarget, _csSwipe.startX, _csSwipe.startY, _csSwipe.curX, _csSwipe.curY);
  }
}

function csMirrorMouseUp(e) {
  if (!_csSwipe.active) return;
  _csSwipe.active = false;
  _csSwipeRemoveArrow();
  var dx = _csSwipe.curX - _csSwipe.startX;
  var dy = _csSwipe.curY - _csSwipe.startY;
  var dist = Math.sqrt(dx*dx + dy*dy);
  if (dist < 10) {
    csMirrorClick(e);
  } else {
    _csSendSwipe(e.currentTarget, _csSwipe.startX, _csSwipe.startY, _csSwipe.curX, _csSwipe.curY);
  }
}

function _csSwipeDrawArrow(container, x1, y1, x2, y2) {
  _csSwipeRemoveArrow();
  var svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.id = 'csSwipeArrow';
  svg.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:15';
  svg.setAttribute('width','100%'); svg.setAttribute('height','100%');
  var defs = document.createElementNS('http://www.w3.org/2000/svg','defs');
  var marker = document.createElementNS('http://www.w3.org/2000/svg','marker');
  marker.setAttribute('id','sw-arrow'); marker.setAttribute('markerWidth','8');
  marker.setAttribute('markerHeight','6'); marker.setAttribute('refX','6');
  marker.setAttribute('refY','3'); marker.setAttribute('orient','auto');
  var poly = document.createElementNS('http://www.w3.org/2000/svg','polygon');
  poly.setAttribute('points','0 0, 8 3, 0 6'); poly.setAttribute('fill','rgba(96,165,250,0.9)');
  marker.appendChild(poly); defs.appendChild(marker); svg.appendChild(defs);
  var line = document.createElementNS('http://www.w3.org/2000/svg','line');
  line.setAttribute('x1',x1); line.setAttribute('y1',y1);
  line.setAttribute('x2',x2); line.setAttribute('y2',y2);
  line.setAttribute('stroke','rgba(96,165,250,0.7)'); line.setAttribute('stroke-width','2');
  line.setAttribute('stroke-dasharray','5 3'); line.setAttribute('marker-end','url(#sw-arrow)');
  svg.appendChild(line);
  var dot = document.createElementNS('http://www.w3.org/2000/svg','circle');
  dot.setAttribute('cx',x1); dot.setAttribute('cy',y1); dot.setAttribute('r','5');
  dot.setAttribute('fill','rgba(96,165,250,0.5)');
  svg.appendChild(dot);
  if (container.style.position !== 'relative' && container.style.position !== 'absolute') {
    container.style.position = 'relative';
  }
  container.appendChild(svg);
}

function _csSwipeRemoveArrow() {
  var old = document.getElementById('csSwipeArrow');
  if (old) old.remove();
}

function _csSendSwipe(container, x1, y1, x2, y2) {
  var imgEl = container.querySelector('img') || container;
  var rect  = imgEl.getBoundingClientRect();
  var dw    = window._csDeviceWidth  || 1080;
  var dh    = window._csDeviceHeight || 1920;
  var scaleX = dw / rect.width;
  var scaleY = dh / rect.height;
  var devX1 = Math.round(x1 * scaleX), devY1 = Math.round(y1 * scaleY);
  var devX2 = Math.round(x2 * scaleX), devY2 = Math.round(y2 * scaleY);

  csLtAppend('user','scroll','','↕ ('+devX1+','+devY1+')→('+devX2+','+devY2+')', 'ok', '');

  fetch('/capture/scroll', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      session_id: _cs.sessionId,
      start_x: devX1, start_y: devY1,
      end_x: devX2, end_y: devY2
    })
  }).then(function(r){ return r.json(); })
    .then(function(d){
      if (!d.ok) console.warn('scroll error', d);
    }).catch(function(err){ console.error(err); });
}
