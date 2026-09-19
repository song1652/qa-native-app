function csSetContext(ctx, btn) {
  _cs.context = ctx;
  document.getElementById('cs-ctx-native').classList.toggle('active', ctx==='native');
  document.getElementById('cs-ctx-webview').classList.toggle('active', ctx==='webview');
}

// ── Hierarchy XML Tree ─────────────────────────────────────────────────
var _csHierarchyDom = null;   // parsed DOMDocument
var _csNodeIdMap = {};        // nodeId (string) → XML element

function csParseXMLBounds(boundsStr) {
  // Android: "[x1,y1][x2,y2]"
  var m = boundsStr && boundsStr.match(/\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]/);
  if (!m) return null;
  return { x1: +m[1], y1: +m[2], x2: +m[3], y2: +m[4] };
}

function csParseNodeBounds(xmlNode) {
  // Android: bounds attribute
  var b = csParseXMLBounds(xmlNode.getAttribute('bounds'));
  if (b) return b;
  // iOS: x, y, width, height attributes
  var x = xmlNode.getAttribute('x'), y = xmlNode.getAttribute('y');
  var w = xmlNode.getAttribute('width'), h = xmlNode.getAttribute('height');
  if (x !== null && y !== null && w !== null && h !== null) {
    return { x1: +x, y1: +y, x2: +x + +w, y2: +y + +h };
  }
  return null;
}

/**
 * 디바이스 논리 해상도 반환.
 * iOS: AppiumAUT 루트에 width/height 없음 → 첫 번째 자식(Application)에서 읽음.
 * Android: 루트 bounds 또는 width/height 속성 사용.
 */
function _csGetDeviceDimensions() {
  if (!_csHierarchyDom) return { w: 1080, h: 2400 };
  var root = _csHierarchyDom.documentElement;

  // 1) 루트 직접 읽기 (Android 방식)
  var rw = parseInt(root.getAttribute('width'));
  var rh = parseInt(root.getAttribute('height'));
  if (rw > 0 && rh > 0) return { w: rw, h: rh };

  // 2) 루트 bounds 속성 (Android fallback)
  var rb = csParseNodeBounds(root);
  if (rb) {
    var bw = rb.x2 - rb.x1, bh = rb.y2 - rb.y1;
    if (bw > 0 && bh > 0) return { w: bw, h: bh };
  }

  // 3) iOS: AppiumAUT 자식(Application)에서 읽기
  for (var i = 0; i < root.children.length; i++) {
    var child = root.children[i];
    var cw = parseInt(child.getAttribute('width'));
    var ch = parseInt(child.getAttribute('height'));
    if (cw > 0 && ch > 0) return { w: cw, h: ch };
    var cb = csParseNodeBounds(child);
    if (cb) {
      var cbw = cb.x2 - cb.x1, cbh = cb.y2 - cb.y1;
      if (cbw > 0 && cbh > 0) return { w: cbw, h: cbh };
    }
  }

  return { w: 1080, h: 2400 }; // 최후 fallback
}

function csNodeShortLabel(node) {
  // Android: class / resource-id / text / content-desc
  // iOS:     type  / name         / label / value
  var cls  = (node.getAttribute('class') || '').split('.').pop();
  var type = (node.getAttribute('type')  || '').replace('XCUIElementType', '');
  var rid  = node.getAttribute('resource-id') || '';
  var txt  = (node.getAttribute('text')   || '').trim();
  var cid  = (node.getAttribute('content-desc') || '').trim();
  var name = (node.getAttribute('name')   || '').trim();
  var lbl  = (node.getAttribute('label')  || '').trim();

  var tag   = cls || type || node.tagName || 'node';
  var annot = rid  ? ' #' + rid.split('/').pop()
            : cid  ? ' "' + cid.substring(0, 18)  + '"'
            : txt  ? ' "' + txt.substring(0, 18)  + '"'
            : name ? ' "' + name.substring(0, 18) + '"'
            : lbl  ? ' "' + lbl.substring(0, 18)  + '"'
            : '';
  return tag + annot;
}

function csRenderLocatorCards(attrs) {
  var cards = [];
  var isIos = !attrs['class'] && (attrs['type'] || attrs['name'] !== undefined);

  if (isIos) {
    // iOS XCUITest locator 전략 — label 우선(사람이 읽는 텍스트), name fallback
    var labelVal = attrs['label'] || '';
    var nameVal  = attrs['name']  || '';
    var accId = labelVal || nameVal;
    if (accId)
      cards.push({ strategy: 'accessibility-id', stars: 5, value: accId });
    var typeVal = attrs['type'] || '';
    if (typeVal && labelVal)
      cards.push({ strategy: 'predicate string', stars: 4, value: 'type == "' + typeVal + '" AND label == "' + labelVal + '"' });
    else if (typeVal)
      cards.push({ strategy: 'predicate string', stars: 3, value: 'type == "' + typeVal + '"' });
    if (typeVal)
      cards.push({ strategy: 'xpath', stars: 2, value: '//' + typeVal });
  } else {
    // Android UiAutomator2 locator 전략
    if (attrs['resource-id'])
      cards.push({ strategy: 'resource-id', stars: 5, value: attrs['resource-id'] });
    if (attrs['content-desc'])
      cards.push({ strategy: 'accessibility-id', stars: 4, value: attrs['content-desc'] });
    if (attrs['text'] && attrs['text'].trim())
      cards.push({ strategy: 'text', stars: 3, value: attrs['text'] });
    if (attrs['class']) {
      var xpath = '//' + attrs['class'].replace(/\./g, '/');
      cards.push({ strategy: 'xpath', stars: 1, value: xpath });
    }
  }
  if (!cards.length) return '<span style="color:var(--text3)">locator 없음</span>';
  var maxStars = Math.max.apply(null, cards.map(function(c){ return c.stars; }));
  return cards.map(function(c) {
    var stars = '★'.repeat(c.stars) + '☆'.repeat(5 - c.stars);
    var badge = c.stars >= 4 ? 'stable' : (c.stars >= 3 ? 'medium' : 'low');
    var badgeLabel = c.stars >= 4 ? '안정' : (c.stars >= 3 ? '보통' : '낮음');
    var rec = c.stars === maxStars;
    var strategyEsc = esc(c.strategy).replace(/'/g,'\\\'');
    var valueEsc = esc(c.value).replace(/'/g,'\\\'');
    var alreadyApproved = _cs.approvedLocators.some(function(l){ return l.strategy === c.strategy && l.value === c.value; });
    var approveBtn = alreadyApproved
      ? '<button class="cs-btn" style="padding:1px 7px;font-size:10px;line-height:1.4;opacity:.5;cursor:default" disabled>승인됨 ✓</button>'
      : '<button class="cs-btn" style="padding:1px 7px;font-size:10px;line-height:1.4;color:#34d399;border-color:rgba(52,211,153,.4)" onclick="csApproveLocator(\'' + strategyEsc + '\',\'' + valueEsc + '\',' + c.stars + ',this)">승인 ✓</button>';
    return '<div class="cs-loc-card' + (rec ? ' recommended' : '') + '">'
      + '<div class="cs-loc-strategy" style="display:flex;align-items:center;justify-content:space-between">'
      + '<span>' + esc(c.strategy) + ' <span class="cs-loc-badge ' + badge + '">' + badgeLabel + '</span></span>'
      + '<span style="display:flex;gap:4px">'
      + '<button class="cs-btn" style="padding:1px 7px;font-size:10px;line-height:1.4" onclick="csValidateLocator(\'' + strategyEsc + '\',\'' + valueEsc + '\',this)">검증</button>'
      + approveBtn
      + '</span>'
      + '</div>'
      + '<div class="cs-loc-stars">' + stars + '</div>'
      + '<div class="cs-loc-value">' + esc(c.value) + '</div>'
      + '<div class="cs-loc-validate-result" style="font-size:10px;margin-top:4px"></div>'
      + '</div>';
  }).join('');
}

function csApproveLocator(strategy, value, rating, btn) {
  var already = _cs.approvedLocators.some(function(l){ return l.strategy === strategy && l.value === value; });
  if (!already) {
    _cs.approvedLocators.push({ strategy: strategy, value: value, rating: rating });
  }
  btn.textContent = '승인됨 ✓';
  btn.disabled = true;
  btn.style.opacity = '0.5';
  btn.style.cursor = 'default';
  btn.style.color = '';
  btn.style.borderColor = '';
  btn.removeAttribute('onclick');
}

function csValidateLocator(strategy, value, btn) {
  var resultEl = btn.closest('.cs-loc-card').querySelector('.cs-loc-validate-result');
  resultEl.textContent = '검증 중...'; resultEl.style.color = 'var(--text3)';
  fetch('/capture/validate_locator', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: _cs.sessionId, strategy: strategy, value: value})
  }).then(function(r){ return r.json(); }).then(function(d){
    if (!d.ok) { resultEl.textContent = '❌ ' + (d.error||'오류'); resultEl.style.color = 'var(--fail)'; return; }
    if (d.unique) {
      resultEl.textContent = '✅ 유일 (1개 매칭) — 신뢰도: ' + d.confidence;
      resultEl.style.color = '#34d399';
    } else if (d.match_count === 0) {
      resultEl.textContent = '⚠️ 매칭 없음 — hierarchy 새로고침 후 재시도';
      resultEl.style.color = '#fbbf24';
    } else {
      resultEl.textContent = '⚠️ ' + d.match_count + '개 매칭 — 신뢰도: ' + d.confidence;
      resultEl.style.color = '#fbbf24';
    }
  }).catch(function(err){
    resultEl.textContent = '❌ 오류: ' + err; resultEl.style.color = 'var(--fail)';
  });
}

function csRenderXMLNode(xmlNode, depth, pathId) {
  if (xmlNode.nodeType !== 1) return '';
  var children = Array.from(xmlNode.children);
  var hasChildren = children.length > 0;
  var label = csNodeShortLabel(xmlNode);
  // Android bounds string, iOS 는 빈 문자열 (csParseNodeBounds로 처리)
  var bounds = xmlNode.getAttribute('bounds') || '';
  _csNodeIdMap[pathId] = xmlNode;
  var indent = depth * 14;
  var childHtml = hasChildren
    ? children.map(function(c, i) { return csRenderXMLNode(c, depth + 1, pathId + '-' + i); }).join('')
    : '';
  return '<div class="cs-tree-node" data-nid="' + esc(pathId) + '">'
    + '<div class="cs-tree-header" style="padding-left:' + indent + 'px"'
    + ' onclick="csSelectTreeNode(this)"'
    + ' onmouseenter="csHoverNode(this,' + JSON.stringify(bounds) + ')"'
    + ' onmouseleave="csHoverNodeEnd()"'
    + '>'
    + (hasChildren
        ? '<span class="cs-tree-toggle" onclick="csToggleTreeNode(event,this)">▶</span>'
        : '<span class="cs-tree-toggle" style="opacity:.25">·</span>')
    + '<span class="cs-tree-label">' + esc(label) + '</span>'
    + (bounds ? '<span class="cs-tree-bounds">' + esc(bounds) + '</span>' : '')
    + '</div>'
    + (hasChildren ? '<div class="cs-tree-children" style="display:none">' + childHtml + '</div>' : '')
    + '</div>';
}

function csToggleTreeNode(event, toggleEl) {
  event.stopPropagation();
  var nodeEl = toggleEl.closest('.cs-tree-node');
  var children = nodeEl && nodeEl.querySelector(':scope > .cs-tree-children');
  if (!children) return;
  var open = children.style.display !== 'none';
  children.style.display = open ? 'none' : '';
  toggleEl.textContent = open ? '▶' : '▼';
}

function csSelectTreeNode(headerEl, skipScroll) {
  document.querySelectorAll('.cs-tree-header.selected').forEach(function(el){ el.classList.remove('selected'); });
  headerEl.classList.add('selected');
  var nodeEl = headerEl.closest('.cs-tree-node');
  var nid = nodeEl && nodeEl.getAttribute('data-nid');
  var xmlNode = nid && _csNodeIdMap[nid];
  if (!xmlNode) return;

  // Collect attrs
  var attrs = {};
  for (var i = 0; i < xmlNode.attributes.length; i++) {
    attrs[xmlNode.attributes[i].name] = xmlNode.attributes[i].value;
  }

  // Detail panel — Android + iOS 속성 통합
  var isIos = !attrs['class'] && (attrs['type'] || attrs['name'] !== undefined);
  var detailKeys = isIos
    ? ['type','name','label','value','enabled','visible','accessible','x','y','width','height','index','bundleId']
    : ['class','resource-id','content-desc','text','bounds','clickable','enabled','focusable','scrollable','package','index'];
  var detail = document.getElementById('cs-element-detail');
  detail.innerHTML = detailKeys.filter(function(k){ return attrs[k] !== undefined; }).map(function(k){
    return '<div class="cs-detail-attr">'
      + '<span class="cs-detail-key">' + esc(k) + '</span>'
      + '<span class="cs-detail-val">' + esc(attrs[k]) + '</span>'
      + '</div>';
  }).join('') || '<span style="color:var(--text3)">속성 없음</span>';

  // Save selected attrs for Step 추가
  _cs.selectedNodeAttrs = attrs;

  // Locator panel
  document.getElementById('cs-locators').innerHTML = csRenderLocatorCards(attrs);

  // Step 추가 섹션 표시 및 서브패널 초기화
  var stepHint = document.getElementById('cs-step-hint');
  if (stepHint) stepHint.style.display = 'none';
  var addStepSection = document.getElementById('cs-add-step-section');
  if (addStepSection) addStepSection.style.display = '';
  // 선택 요소 레이블 업데이트
  var selectedLabel = document.getElementById('cs-selected-label');
  if (selectedLabel) selectedLabel.textContent = _csNodeLabel();
  var inputArea = document.getElementById('cs-step-input-area');
  if (inputArea) inputArea.style.display = 'none';
  var assertMenu = document.getElementById('cs-assert-menu');
  if (assertMenu) assertMenu.style.display = 'none';
  var assertTextArea = document.getElementById('cs-assert-text-area');
  if (assertTextArea) assertTextArea.style.display = 'none';

  if (!skipScroll) headerEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });

  // 미러에 하이라이트 박스 표시
  // Android: attrs['bounds'] 사용 / iOS: x,y,width,height로 bounds 문자열 생성
  var highlightBounds = attrs['bounds'] || null;
  if (!highlightBounds && attrs['x'] !== undefined) {
    var hx1 = +attrs['x'], hy1 = +attrs['y'];
    var hx2 = hx1 + +attrs['width'], hy2 = hy1 + +attrs['height'];
    highlightBounds = '[' + hx1 + ',' + hy1 + '][' + hx2 + ',' + hy2 + ']';
  }
  csHighlightElementOnMirror(highlightBounds, _csNodeLabel());
}

// ---- Step 추가 헬퍼 함수 ----

// 선택된 노드에서 가장 좋은 locator 추출
// 미러 화면에 선택 요소 하이라이트 박스 표시 (Appium Inspector 스타일)
// hover 시 미러 파란색 하이라이트 (선택 보라색과 별도)
function csHoverNode(headerEl, boundsStr) {
  if (!boundsStr) return;
  var hov = document.getElementById('cs-hover-highlight');
  if (!hov) return;
  var b = csParseXMLBounds(boundsStr);
  if (!b) return;
  var _dimH = _csGetDeviceDimensions();
  var devW = _dimH.w, devH = _dimH.h;
  var container = document.getElementById('cs-mirror-container');
  if (!container) return;
  var cW = container.clientWidth, cH = container.clientHeight;
  if (!cW || !cH) return;
  var imgAspect = devW / devH, conAspect = cW / cH;
  var scaleX, scaleY, offsetX = 0, offsetY = 0;
  if (imgAspect > conAspect) { scaleX = cW / devW; scaleY = scaleX; offsetY = (cH - devH * scaleY) / 2; }
  else { scaleY = cH / devH; scaleX = scaleY; offsetX = (cW - devW * scaleX) / 2; }
  hov.style.left   = (offsetX + b.x1 * scaleX) + 'px';
  hov.style.top    = (offsetY + b.y1 * scaleY) + 'px';
  hov.style.width  = Math.max(1, (b.x2 - b.x1) * scaleX) + 'px';
  hov.style.height = Math.max(1, (b.y2 - b.y1) * scaleY) + 'px';
  hov.style.display = 'block';
}

function csHoverNodeEnd() {
  var hov = document.getElementById('cs-hover-highlight');
  if (hov) hov.style.display = 'none';
}


function csHighlightElementOnMirror(boundsStr, label) {
  var box = document.getElementById('cs-element-highlight');
  var lbl = document.getElementById('cs-element-highlight-label');
  if (!box || !lbl) return;

  if (!boundsStr) { box.style.display = 'none'; lbl.style.display = 'none'; return; }

  var b = csParseXMLBounds(boundsStr);
  if (!b) { box.style.display = 'none'; lbl.style.display = 'none'; return; }

  // 디바이스 해상도 (iOS AppiumAUT 루트 자식까지 탐색하는 통합 함수 사용)
  var _dim = _csGetDeviceDimensions();
  var devW = _dim.w, devH = _dim.h;

  // 미러 컨테이너 실제 크기
  var container = document.getElementById('cs-mirror-container');
  if (!container) return;
  var cW = container.clientWidth;
  var cH = container.clientHeight;
  if (!cW || !cH) return;

  // 스케일: 컨테이너 내부에서 이미지가 aspect-ratio를 유지하며 표시되는 영역
  // object-fit:contain → letterbox 방식
  var imgAspect = devW / devH;
  var conAspect = cW / cH;
  var scaleX, scaleY, offsetX = 0, offsetY = 0;
  if (imgAspect > conAspect) {
    scaleX = cW / devW; scaleY = scaleX;
    offsetY = (cH - devH * scaleY) / 2;
  } else {
    scaleY = cH / devH; scaleX = scaleY;
    offsetX = (cW - devW * scaleX) / 2;
  }

  var left   = offsetX + b.x1 * scaleX;
  var top    = offsetY + b.y1 * scaleY;
  var width  = (b.x2 - b.x1) * scaleX;
  var height = (b.y2 - b.y1) * scaleY;

  box.style.left   = left   + 'px';
  box.style.top    = top    + 'px';
  box.style.width  = width  + 'px';
  box.style.height = height + 'px';
  box.style.display = '';

  // 레이블: 박스 위 또는 아래에 표시
  lbl.textContent = label || '';
  var lblTop = top - 18;
  if (lblTop < 0) lblTop = top + height + 2;
  lbl.style.left = left + 'px';
  lbl.style.top  = lblTop + 'px';
  lbl.style.display = '';
}

function _csBestLocator() {
  var attrs = _cs.selectedNodeAttrs;
  if (!attrs) return null;
  // 승인된 locator 우선
  if (_cs.approvedLocators.length > 0) {
    var a = _cs.approvedLocators[0];
    return {strategy: a.strategy, value: a.value};
  }
  var isIos = !attrs['class'] && (attrs['type'] || attrs['name'] !== undefined);
  if (isIos) {
    // iOS: label(사람이 읽는 텍스트) > name(번들ID) > predicate > xpath
    // label 우선: XCUITest ACCESSIBILITY_ID는 label/name 모두 매칭하고,
    // label을 쓰면 화면 밖 요소도 자동 스크롤하여 탭 가능
    var accId = attrs['label'] || attrs['name'] || '';
    if (accId) return {strategy: 'accessibility-id', value: accId};
    if (attrs['type']) return {strategy: 'xpath', value: '//' + attrs['type']};
  } else {
    // Android: app-specific resource-id > content-desc > text > generic-id > class
    // android:id/* 같은 시스템 공용 ID는 비유일하므로 text/content-desc를 우선 사용
    var rid = attrs['resource-id'] || '';
    var isGenericId = !rid || rid.startsWith('android:id/') || rid.startsWith('android:attr/');
    if (rid && !isGenericId) return {strategy: 'resource-id', value: rid};
    if (attrs['content-desc']) return {strategy: 'accessibility-id', value: attrs['content-desc']};
    if (attrs['text']) return {strategy: 'text', value: attrs['text']};
    if (rid) return {strategy: 'resource-id', value: rid};  // 마지막 fallback
    if (attrs['class']) return {strategy: 'class', value: attrs['class']};
  }
  return null;
}

// 요소 label (트리 표시용)
function _csNodeLabel() {
  var attrs = _cs.selectedNodeAttrs;
  if (!attrs) return '선택된 요소';
  // Android
  var rid = attrs['resource-id'] || '';
  if (rid) return rid.split('/').pop() || rid;
  if (attrs['text']) return attrs['text'];
  if (attrs['content-desc']) return attrs['content-desc'];
  // iOS
  if (attrs['name']) return attrs['name'];
  if (attrs['label']) return attrs['label'];
  return attrs['class'] || attrs['type'] || '요소';
}

function csAddStep(type) {
  var loc = _csBestLocator();
  if (!loc) { alert('요소를 먼저 선택하세요.'); return; }
  var idx = _cs.actions.length;
  _cs.actions.push({
    index: idx + 1,
    action: type,
    strategy: loc.strategy,
    value: loc.value,
    label: _csNodeLabel(),
    context: _cs.context,
    expected: ''
  });
  csRenderTimeline();
  var tl = document.getElementById('cs-timeline');
  if (tl) tl.scrollTop = tl.scrollHeight;
}

function csAddStepInput() {
  var loc = _csBestLocator();
  if (!loc) { alert('요소를 먼저 선택하세요.'); return; }
  document.getElementById('cs-step-input-area').style.display = '';
  document.getElementById('cs-assert-menu').style.display = 'none';
  document.getElementById('cs-assert-text-area').style.display = 'none';
  document.getElementById('cs-step-input-val').focus();
}

function csConfirmInput() {
  var val = document.getElementById('cs-step-input-val').value;
  var loc = _csBestLocator();
  if (!loc) return;
  var idx = _cs.actions.length;
  _cs.actions.push({
    index: idx + 1,
    action: 'input',
    strategy: loc.strategy,
    value: loc.value,
    input_text: val,
    label: _csNodeLabel(),
    context: _cs.context,
    expected: ''
  });
  document.getElementById('cs-step-input-val').value = '';
  document.getElementById('cs-step-input-area').style.display = 'none';
  csRenderTimeline();
  var tl = document.getElementById('cs-timeline');
  if (tl) tl.scrollTop = tl.scrollHeight;
}

function csCancelStepInput() {
  document.getElementById('cs-step-input-area').style.display = 'none';
  document.getElementById('cs-step-input-val').value = '';
}

function csToggleAssertMenu() {
  var m = document.getElementById('cs-assert-menu');
  var loc = _csBestLocator();
  if (!loc) { alert('요소를 먼저 선택하세요.'); return; }
  m.style.display = m.style.display === 'none' ? '' : 'none';
  document.getElementById('cs-step-input-area').style.display = 'none';
  document.getElementById('cs-assert-text-area').style.display = 'none';
}

function csAddAssert(assertType) {
  document.getElementById('cs-assert-menu').style.display = 'none';
  if (assertType === 'text_visible') {
    document.getElementById('cs-assert-text-area').style.display = '';
    var textVal = document.getElementById('cs-assert-text-val');
    textVal.dataset.assertType = assertType;
    textVal.focus();
  } else {
    _csCommitAssert(assertType, '');
  }
}

function csConfirmAssertText() {
  var val = document.getElementById('cs-assert-text-val').value;
  _csCommitAssert('text_visible', val);
  document.getElementById('cs-assert-text-val').value = '';
  document.getElementById('cs-assert-text-area').style.display = 'none';
}

function csCancelAssert() {
  document.getElementById('cs-assert-menu').style.display = 'none';
  document.getElementById('cs-assert-text-area').style.display = 'none';
}

function _csCommitAssert(assertType, assertValue) {
  var loc = _csBestLocator();
  if (!loc) return;
  var idx = _cs.actions.length;
  _cs.actions.push({
    index: idx + 1,
    action: 'assertion',
    assertion_type: assertType,
    assertion_value: assertValue,
    strategy: loc.strategy,
    value: loc.value,
    label: _csNodeLabel(),
    context: _cs.context,
    expected: ''
  });
  csRenderTimeline();
  var tl = document.getElementById('cs-timeline');
  if (tl) tl.scrollTop = tl.scrollHeight;
}

// ---- Step 추가 헬퍼 함수 끝 ----

function csFindSmallestNodeAt(x, y, xmlNode) {
  if (xmlNode.nodeType !== 1) return null;
  var b = csParseNodeBounds(xmlNode);  // Android + iOS 통합 파서 사용
  if (!b || x < b.x1 || x > b.x2 || y < b.y1 || y > b.y2) return null;
  var result = xmlNode;
  var resultArea = (b.x2 - b.x1) * (b.y2 - b.y1);
  for (var i = 0; i < xmlNode.children.length; i++) {
    var child = csFindSmallestNodeAt(x, y, xmlNode.children[i]);
    if (child) {
      var cb = csParseNodeBounds(child);  // Android + iOS 통합
      if (cb) {
        var area = (cb.x2 - cb.x1) * (cb.y2 - cb.y1);
        if (area <= resultArea) { result = child; resultArea = area; }
      }
    }
  }
  return result;
}

function csHighlightNodeInTree(xmlNode) {
  // Find nid for xmlNode
  var foundNid = null;
  for (var nid in _csNodeIdMap) {
    if (_csNodeIdMap[nid] === xmlNode) { foundNid = nid; break; }
  }
  if (!foundNid) return;
  var nodeEl = document.querySelector('.cs-tree-node[data-nid="' + foundNid + '"]');
  if (!nodeEl) return;
  // Expand all ancestors
  var parent = nodeEl.parentElement;
  while (parent) {
    if (parent.classList && parent.classList.contains('cs-tree-children')) {
      parent.style.display = '';
      var toggle = parent.previousElementSibling && parent.previousElementSibling.querySelector('.cs-tree-toggle');
      if (toggle) toggle.textContent = '▼';
    }
    parent = parent.parentElement;
  }
  var header = nodeEl.querySelector(':scope > .cs-tree-header');
  if (header) csSelectTreeNode(header, false);
}

function csRefreshHierarchy(retryCount) {
  retryCount = retryCount || 0;
  var treeEl = document.getElementById('cs-hierarchy-tree');
  if(treeEl && retryCount === 0) treeEl.innerHTML = '<span style="color:var(--text3);font-size:11px">⏳ 로딩 중...</span>';

  // 드라이버가 살아있으면 fresh snapshot → 파일 로드, 없으면 바로 파일 로드
  if(!_cs.sessionId){ _csLoadHierarchyFromFile(retryCount); return; }

  fetch('/capture/driver_alive').then(function(r){ return r.json(); }).then(function(d){
    if(d.alive){
      fetch('/capture/snapshot', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({session_id: _cs.sessionId, context: _cs.context})
      }).then(function(){ _csLoadHierarchyFromFile(retryCount); })
        .catch(function(){ _csLoadHierarchyFromFile(retryCount); });
    } else {
      // 드라이버 없음 — 디스크 파일에서 바로 로드
      _csLoadHierarchyFromFile(retryCount);
    }
  }).catch(function(){ _csLoadHierarchyFromFile(retryCount); });
}

function _csLoadHierarchyFromFile(retryCount) {
  retryCount = retryCount || 0;
  fetch('/capture/hierarchy?session_id=' + encodeURIComponent(_cs.sessionId) + '&context=' + _cs.context)
    .then(function(r){ return r.json(); }).then(function(d){
      var treeEl = document.getElementById('cs-hierarchy-tree');
      if (d.hierarchy) {
        try {
          _csNodeIdMap = {};
          var parser = new DOMParser();
          var xmlDoc = parser.parseFromString(d.hierarchy, 'application/xml');
          var parseErr = xmlDoc.querySelector('parsererror');
          if (parseErr) throw new Error('XML parse error');
          _csHierarchyDom = xmlDoc;
          treeEl.innerHTML = csRenderXMLNode(xmlDoc.documentElement, 0, '0');
          // Expand ALL tree nodes
          treeEl.querySelectorAll('.cs-tree-children').forEach(function(el){ el.style.display = ''; });
          treeEl.querySelectorAll('.cs-tree-toggle').forEach(function(el){ el.textContent = '▼'; });
        } catch (e) {
          treeEl.textContent = d.hierarchy.substring(0, 8000);
        }
      } else if (retryCount < 3) {
        // hierarchy 없음 → 드라이버 준비 중일 수 있으므로 재시도
        treeEl.innerHTML = '<span style="color:var(--text3)">⏳ hierarchy 대기 중... (' + (retryCount + 1) + '/3)</span>';
        setTimeout(function(){ csRefreshHierarchy(retryCount + 1); }, 3000);
      } else {
        treeEl.innerHTML = '<span style="color:var(--text3)">hierarchy 없음</span>';
        _csHierarchyDom = null;
      }
    }).catch(function(err){
      document.getElementById('cs-hierarchy-tree').textContent = '오류: ' + err;
    });
}
