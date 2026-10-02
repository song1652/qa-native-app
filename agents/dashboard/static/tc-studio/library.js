// TC 스튜디오 — 라이브러리 화면: 트리·필터·그리드·셀 편집·일괄 편집 (목업 1번 화면, PRD F5.1~F5.4)
(function (NS) {
  'use strict';

  const { state, api, esc, $, $$, toast } = NS;
  const open = new Set();          // 펼친 트리 가지 (path.join('\u0001'))
  const FETCH_PAGE = 1000;         // 서버 limit 상한. 넘으면 offset으로 이어 받는다
  const ROW_CHUNK = 150;           // 한 번에 그리는 행 수. 나머지는 스크롤이 끝에 닿을 때 붙인다
  const TREE_KEY = 'tcs-tree-hidden';
  let root = null;
  let listSeq = 0;
  let shown = 0;
  let moreObserver = null;

  const opt = (v, label, cur) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(label)}</option>`;

  NS.library = { html, mount, refresh, reloadList };

  function html() {
    return `
  <section class="screen" id="screen-library" data-screen="library">
        <div class="filterbar" role="search">
          <div class="search"><input class="input" id="lib-search" data-id="lib-search" placeholder="제목, Step, Expected, UI 문구 검색  ( / )" autocomplete="off"></div>
          <select class="fselect" id="lib-filter-result" data-id="lib-filter-result" aria-label="실행 결과">
            ${opt('', '실행 결과 전체')}${opt('none', '미실행')}${opt('pass', '통과')}${opt('fail', '실패')}${opt('not_test', '테스트 안 함')}${opt('na', 'N/A')}</select>
          <select class="fselect app-only" id="lib-filter-platform" aria-label="플랫폼">${opt('', '플랫폼 전체')}${opt('android', 'And')}${opt('ios', 'iOS')}</select>
          <button class="fchip app-only" id="lib-filter-mismatch" aria-pressed="false">And·iOS 결과가 다른 것만</button>
          <select class="fselect" id="lib-filter-status" data-id="lib-filter-status" aria-label="검토 상태">
            ${opt('', '검토 상태 전체')}${Object.entries(NS.STATUS_LABEL).map(([v, l]) => opt(v, l)).join('')}${opt('imported', '가져옴')}</select>
          <select class="fselect" id="lib-filter-priority" data-id="lib-filter-priority" aria-label="우선순위">
            ${opt('', '우선순위 전체')}${NS.PRIORITIES.map((p) => opt(p, p)).join('')}${opt('-', '미지정')}</select>
          <select class="fselect" id="lib-filter-source" data-id="lib-filter-source" aria-label="출처">
            ${opt('', '출처 전체')}${opt('xlsx', '엑셀 가져오기')}${opt('conf', 'Confluence')}${opt('figma', 'Figma')}${opt('file', '파일·붙여넣기')}</select>
        </div>
        <div class="grid-meta">
          ${NS.sourceWatch ? '<button class="fchip" data-id="lib-filter-needs-review" id="lib-filter-needs-review" aria-pressed="false">재검토 필요 <span class="n" id="n-review">0</span></button>' : ''}
          <button class="fchip" data-id="lib-filter-invalid" id="lib-filter-invalid" aria-pressed="false">검증 오류 <span class="n" id="n-invalid">0</span></button>
          <button class="btn-sm" data-id="lib-filter-reset" id="lib-filter-reset">초기화</button>

          <button class="btn-sm" data-id="tree-toggle" id="tree-toggle" aria-pressed="false" title="계층 트리를 숨겨 그리드를 넓게 봅니다">트리 숨기기</button>
          <button class="btn-sm" id="grid-extra-columns" aria-pressed="false">추가 열 보기</button><span class="crumbpath" id="grid-crumb"></span>
          <span id="grid-count" class="num"></span>
          <span class="spacer"></span>
          <span class="faint">더블클릭 또는 Enter로 셀 편집 · <span class="kbd">⌘</span><span class="kbd">↵</span> 저장 · <span class="kbd">Esc</span> 취소</span>
          ${NS.sourceWatch ? '<button class="btn btn-ghost" data-id="btn-check-sources" id="btn-check-sources" title="Confluence·Figma 출처의 새 버전을 확인합니다">출처 변경 확인</button>' : ''}
          <button class="btn btn-primary" data-id="btn-add-case" id="btn-add-case">+ 케이스 추가</button>
        </div>
    <div class="lib no-detail" id="lib">
      <aside class="tree-pane" aria-label="계층 트리">
        <div class="tree-tools"><b>계층 트리</b>
          <input class="input" id="tree-search" data-id="tree-search" placeholder="가지 이름 검색" autocomplete="off">
          <div class="row" style="justify-content:space-between">
            <span class="faint" style="font-size:11px">시트 › 대분류 › 중분류 › 소분류 › 제목</span>
            <button class="icon-btn" data-id="tree-collapse-all" id="tree-collapse-all" title="모두 접기" aria-label="모두 접기">⊟</button>
          </div>
        </div>
        <ul class="tree" id="tree" data-id="lib-tree" role="tree"></ul>
        <div class="tree-legend"><span><i class="dot d-draft"></i>초안</span><span><i class="dot d-review"></i>재검토</span><span><i class="dot d-err"></i>검증 오류</span></div>
      </aside>
      <div class="center">
        <div id="lib-banners"></div>
        <div class="grid-wrap" id="grid-wrap">
          <table class="grid" id="grid" data-id="lib-grid" aria-label="케이스 그리드">
            <colgroup><col style="width:34px"><col style="width:20px"><col style="width:44px"><col style="width:96px"><col class="c-l2" style="width:96px"><col class="c-l3" style="width:96px"><col style="width:200px"><col style="width:150px"><col style="width:200px"><col style="width:240px"><col style="width:74px"><col class="web-result" style="width:100px"><col class="app-result" style="width:92px"><col class="app-result" style="width:92px"><col style="width:130px"></colgroup>
            <thead><tr>
              <th><input type="checkbox" id="grid-check-all" data-id="grid-check-all" aria-label="전체 선택"></th>
              <th></th><th class="no"><span class="xl">A</span>No.</th>
              <th><span class="xl">B</span>대분류</th><th><span class="xl">C</span>중분류</th><th><span class="xl">D</span>소분류</th>
              <th><span class="xl">E</span>ID · 제목</th><th><span class="xl">F</span>사전 조건</th><th><span class="xl">G</span>테스트 단계</th>
              <th><span class="xl">H</span>기대 결과</th><th><span class="xl">I</span>우선순위</th><th class="web-result">실행 결과</th><th class="app-result">And</th><th class="app-result">iOS</th><th><span class="xl">M</span>검토</th>
            </tr></thead>
            <tbody id="grid-body"></tbody>
          </table>
        </div>
        <div class="bulkbar" id="bulkbar" data-id="bulk-bar" hidden>
          <b><span id="bulk-n">0</span>건 선택</b>
          <select class="chip-select app-result" data-id="bulk-platform" id="bulk-platform">${opt('android', 'Android')}${opt('ios', 'iOS')}</select>
          <select class="chip-select" data-id="bulk-result" id="bulk-result">${opt('', '실행 결과…')}${opt('none', '미실행')}${opt('pass', '통과')}${opt('fail', '실패')}${opt('not_test', '테스트 안 함')}${opt('na', 'N/A')}</select>
          <select class="chip-select" data-id="bulk-status" id="bulk-status">${opt('', '검토 상태…')}${opt('approved', '승인')}${opt('draft', '초안으로')}${opt('rejected', '반려')}</select>
          <button class="btn-sm" data-id="bulk-move" id="bulk-move">계층 이동…</button>
          <details class="bulk-more"><summary aria-label="일괄 작업 더보기">⋯ 더보기</summary><div>
          <select class="chip-select" data-id="bulk-priority" id="bulk-priority">${opt('', '우선순위…')}${NS.PRIORITIES.map((p) => opt(p, p)).join('')}</select>
          <button class="btn-sm" data-id="bulk-duplicate" id="bulk-duplicate">복제</button>
          <button class="btn btn-danger" data-id="bulk-delete" id="bulk-delete" style="padding:4px 10px;font-size:11px">삭제</button>
          </div></details>
          <span class="spacer"></span>
          <button class="icon-btn" data-id="bulk-clear" id="bulk-clear" aria-label="선택 해제">✕</button>
        </div>
        <div id="lib-empty" hidden>
          <div class="empty" data-id="lib-empty">
            <div class="xl-icon">X</div>
            <h3>라이브러리가 비어 있습니다</h3>
            <p>기존 Full TC 엑셀을 가져오면 시트별 계층 트리와 케이스가 한 번에 들어옵니다. 가져온 케이스는 모두 승인 상태로 시작합니다.</p>
            ${NS.importModal ? '<div class="row" style="justify-content:center"><button class="btn btn-primary" data-id="empty-import-xlsx" id="empty-import-xlsx">엑셀 가져오기</button></div>' : ''}
            <p class="faint" style="font-size:11px">.xlsx · 헤더 행은 자동으로 찾습니다 · 원본 파일은 수정하지 않습니다</p>
          </div>
        </div>
      </div>
      ${NS.detail.html()}
    </div>
  </section>
  <div class="scrim" id="move-modal" data-id="move-modal" hidden>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="mv-title" style="width:min(440px,100%)">
      <div class="panel-head"><span id="mv-title">계층 이동</span><span class="spacer"></span><button class="icon-btn" data-id="move-close" id="move-close" aria-label="닫기">✕</button></div>
      <div class="panel-body" style="display:grid;gap:10px">
        <div class="field"><span class="label">시트 › 대분류 › 중분류 › 소분류</span><select class="select" id="move-target" data-id="move-target"></select></div>
        <div class="field"><span class="label">제목</span><input class="input" id="move-feature" data-id="move-feature" placeholder="비워 두면 기존 제목 유지"></div>
        <div class="row"><span class="spacer"></span><button class="btn btn-ghost" id="move-cancel" data-id="move-cancel">취소</button><button class="btn btn-primary" id="move-confirm" data-id="move-confirm">이동</button></div>
      </div>
    </div>
  </div>
  <div class="scrim" id="dirty-modal" data-id="dirty-modal" hidden>
    <div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="dirty-title" style="width:min(420px,100%)">
      <div class="panel-body" style="display:grid;gap:12px">
        <b id="dirty-title"></b>
        <span class="muted">저장하지 않으면 상세 패널에서 고친 내용이 사라집니다.</span>
        <div class="row"><span class="spacer"></span><button class="btn btn-ghost" id="dirty-cancel" data-id="dirty-cancel">계속 편집</button><button class="btn btn-ghost" id="dirty-discard" data-id="dirty-discard">버리기</button><button class="btn btn-primary" id="dirty-save" data-id="dirty-save">저장</button></div>
      </div>
    </div>
  </div>
  <div class="scrim" id="confirm-modal" data-id="confirm-modal" hidden>
    <div class="modal" role="alertdialog" aria-modal="true" style="width:min(400px,100%)">
      <div class="panel-body" style="display:grid;gap:12px">
        <b id="cf-title"></b>
        <span class="muted">삭제한 케이스는 되돌리기로 복원할 수 있습니다. 엑셀 다음 내보내기부터 빠집니다.</span>
        <div class="row"><span class="spacer"></span><button class="btn btn-ghost" id="cf-cancel" data-id="confirm-cancel">취소</button><button class="btn btn-danger" id="cf-ok" data-id="confirm-ok" style="background:var(--err);color:var(--text)">삭제</button></div>
      </div>
    </div>
  </div>`;
  }

  // ── 데이터 ───────────────────────────────────────────────────
  async function refresh() {
    const empty = !state.suite;
    $('#lib-empty', root).hidden = !empty;
    ['.filterbar', '.grid-meta', '#grid-wrap', '.tree-tools', '#tree'].forEach((s) => { $(s, root).hidden = empty; });
    if (empty) { state.items = []; state.tree = []; return; }
    const { tree } = await api.tree(state.suite);
    state.tree = tree;
    if (!open.size) tree.forEach((n) => { open.add(key(n.path)); (n.children || []).forEach((c) => open.add(key(c.path))); });
    renderTree();
    await reloadList();
    if (NS.sourceWatch) await NS.sourceWatch.renderBanner(root);
    if (NS.refreshSuiteCounts) await NS.refreshSuiteCounts();
  }

  async function reloadList() {
    const seq = ++listSeq;
    const suite = state.suite;
    const query = NS.queryFromFilters(state.filters);
    const { items: first, total } = await api.list(suite, { ...query, limit: FETCH_PAGE });
    let items = first;
    while (items.length < total) {
      const { items: next } = await api.list(suite, { ...query, offset: items.length, limit: FETCH_PAGE });
      if (!next.length) break;
      items = items.concat(next);
    }
    if (seq !== listSeq || suite !== state.suite) return;   // 늦게 도착한 이전 검색 결과는 버린다
    state.items = items;
    state.total = total;
    state.selected.forEach((id) => { if (!items.some((c) => c.case_id === id)) state.selected.delete(id); });
    renderGrid();
    NS.detail.refreshIfOpen();
  }

  const key = (path) => path.join('\u0001');
  const byId = (id) => state.items.find((c) => c.case_id === id);

  // ── 트리 (목업 renderTree 이식) ──────────────────────────────
  const LV = { sheet: 'S', l1: '대', l2: '중', l3: '소', feature: '기' };
  function renderTree() {
    const q = $('#tree-search', root).value.trim();
    const matches = (n) => !q || n.name.includes(q) || (n.children || []).some(matches);
    const node = (n) => {
      if (!matches(n)) return '';
      const has = n.children && n.children.length;
      const isOpen = has && (open.has(key(n.path)) || !!q);
      const sel = state.filters.path === n.path.join('/');
      const dots = `<span class="dots">${n.draft ? `<i class="dot d-draft" title="초안 ${n.draft}"></i>` : ''}${n.needs_review ? '<i class="dot d-review"></i>' : ''}${n.invalid ? `<i class="dot d-err" title="검증 오류 ${n.invalid}"></i>` : ''}</span>`;
      return `<li role="treeitem" aria-expanded="${has ? !!isOpen : ''}">
        <div class="tnode ${isOpen ? 'open' : ''} ${sel ? 'sel' : ''}" data-id="tree-node" tabindex="0" data-path="${esc(n.path.join('/'))}" data-level="${n.level}" data-name="${esc(n.name)}">
          <span class="caret">${has ? '▶' : ''}</span><span class="lvl">${LV[n.level]}</span><span class="nm">${esc(n.name)}</span>${dots}<span class="ct num">${n.count}</span>
        </div>${has && isOpen ? `<ul role="group">${n.children.map(node).join('')}</ul>` : ''}</li>`;
    };
    $('#tree', root).innerHTML = state.tree.map(node).join('');
    $$('#tree .tnode', root).forEach((el) => {
      el.addEventListener('click', () => {
        const path = el.dataset.path.split('/');
        const k = key(path);
        if (open.has(k)) open.delete(k); else open.add(k);
        state.filters.path = state.filters.path === el.dataset.path ? '' : el.dataset.path;
        renderTree();
        reloadList();
      });
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.click(); } });
      el.addEventListener('dragover', (e) => { e.preventDefault(); el.classList.add('drop'); });
      el.addEventListener('dragleave', () => el.classList.remove('drop'));
      el.addEventListener('drop', (e) => {
        e.preventDefault();
        el.classList.remove('drop');
        const id = e.dataTransfer.getData('text/case');
        const target = el.dataset.path.split('/');
        // 기능 가지에 떨어뜨리면 그 기능의 부모 가지로 옮기고 기능명은 유지한다
        const parent = el.dataset.level === 'feature' ? target.slice(0, -1) : target;
        if (id && parent.length >= 2) moveCases([id], parent, '');
      });
    });
  }

  // ── 그리드 (목업 renderGrid·bindGrid 이식) ────────────────────
  function resultSelect(c) {
    const v = c.execution_result || '';
    return `<select class="chip-select result-${v ? v.replace('_', '-') : 'none'}" data-id="grid-result" aria-label="${c.case_id} 실행 결과">${
      Object.entries(NS.RESULT_LABEL).map(([k, l]) => opt(k, l, v)).join('')}</select>`;
  }
  function platformResultSelect(c, platform) {
    const included = (c.platforms || ['android', 'ios']).includes(platform);
    const value = included ? (c.results || {})[platform] || '' : 'na';
    return `<select class="chip-select result-${value || 'none'}" data-platform="${platform}" aria-label="${c.case_id} ${platform} 결과" ${included ? '' : 'disabled'}>${
      Object.entries(NS.RESULT_LABEL).map(([k, l]) => opt(k, l, value)).join('')}</select>`;
  }
  function prioritySelect(c) {
    const cls = c.priority ? c.priority.toLowerCase() : 'is-unset';  // 'empty'는 빈 화면 .empty와 충돌
    return `<select class="chip-select ${cls}" data-id="grid-cell-priority" aria-label="${c.case_id} 우선순위">${
      ['', ...NS.PRIORITIES].map((p) => opt(p, p || '—', c.priority)).join('')}</select>`;
  }
  function expHtml(c) {
    return esc(c.expected) + c.bullets.map((b) =>
      `\n<span class="blt ${b.verified ? '' : 'est'}">- ${esc(b.text)}${b.verified ? '' : ' (추정)'}</span>`).join('');
  }
  function rowHtml(c, i) {
    const prev = state.items[i - 1];
    const hier = [0, 1, 2].map((d) => {
      const rep = prev && prev.sheet === c.sheet && prev.path.slice(0, d + 1).join('/') === c.path.slice(0, d + 1).join('/') && c.path[d];
      return `<td class="${rep ? 'rep' : ''}"><span>${esc(c.path[d])}</span></td>`;
    }).join('');
    const errors = c.issues.filter((x) => x.level === 'error');
    return `<tr data-case="${c.case_id}" class="${state.selected.has(c.case_id) ? 'sel' : ''} ${state.activeId === c.case_id ? 'active' : ''}">
        <td><input type="checkbox" data-id="grid-row-check" aria-label="${c.case_id} 선택" ${state.selected.has(c.case_id) ? 'checked' : ''}></td>
        <td><span class="drag" draggable="true" data-id="grid-row-drag" title="트리로 끌어 계층 이동">⋮⋮</span></td>
        <td class="no">${i + 1}</td>
        ${hier}
        <td><span class="compact-case-id mono">${esc(c.case_id)}</span><div class="cell" data-edit="feature" data-id="grid-cell-feature" tabindex="0">${esc(c.feature)}</div></td>
        <td><div class="cell" data-edit="precondition" data-id="grid-cell-precondition" tabindex="0">${esc(c.precondition)}</div></td>
        <td><div class="cell" data-edit="steps" data-id="grid-cell-steps" tabindex="0">${esc(c.steps.map((s, n) => `${n + 1}. ${s}`).join('\n'))}</div></td>
        <td><div class="cell" data-edit="expected" data-id="grid-cell-expected" tabindex="0">${expHtml(c)}</div>${errors.length ? `<span class="vbadge tag err" title="${esc(errors.map((x) => x.message).join(', '))}">검증 오류 ${errors.length}</span>` : ''}${c.bullets.some((b) => !b.verified) ? ' <span class="vbadge tag warn">추정 문구</span>' : ''}</td>
        <td>${prioritySelect(c)}</td>
        <td class="web-result">${resultSelect(c)}</td>
        <td class="app-result ${!(c.platforms || ['android','ios']).includes('android') ? 'platform-na' : ''}">${platformResultSelect(c, 'android')}</td>
        <td class="app-result ${!(c.platforms || ['android','ios']).includes('ios') ? 'platform-na' : ''}">${platformResultSelect(c, 'ios')}</td>
        <td><div class="etc"><span>id:${c.case_id}</span><span class="pill st-${c.status}" data-id="grid-status-chip">${NS.STATUS_LABEL[c.status]}</span>${c.note ? `<span>${esc(c.note)}</span>` : ''}</div></td>
      </tr>`;
  }
  const moreHtml = () => (shown < state.items.length
    ? `<tr class="grid-more" id="grid-more" data-id="grid-more"><td colspan="15">${shown.toLocaleString()} / ${state.items.length.toLocaleString()}건 표시 · 스크롤하면 더 불러옵니다</td></tr>`
    : '');

  // keep: 저장·선택 뒤 다시 그릴 때 지금까지 펼친 행 수를 유지한다 (스크롤 위치 보존)
  function renderGrid({ keep = false } = {}) {
    shown = Math.min(state.items.length, Math.max(ROW_CHUNK, keep ? shown : 0));
    // 아무 케이스도 쓰지 않는 중·소분류 열은 접어 제목·Step 자리를 넓힌다
    $('#grid', root).classList.toggle('no-l2', !state.items.some((c) => c.path[1]));
    $('#grid', root).classList.toggle('no-l3', !state.items.some((c) => c.path[2]));
    $('#grid-body', root).innerHTML = (state.items.slice(0, shown).map(rowHtml).join('') + moreHtml())
      || `<tr><td colspan="15" style="text-align:center;padding:40px;color:var(--text3)" data-id="grid-empty-filter">조건에 맞는 케이스가 없습니다.</td></tr>`;
    $('#grid-crumb', root).textContent = state.filters.path.replaceAll('/', ' › ') || state.suite;
    $('#grid-count', root).textContent = `${state.total}건`;
    $('#n-invalid', root).textContent = state.items.filter((c) => c.has_error).length;
    bindRows($$('#grid-body tr[data-case]', root));
    watchMore();
    updateBulk();
  }

  function appendRows() {
    const from = shown;
    shown = Math.min(state.items.length, shown + ROW_CHUNK);
    if (shown === from) return;
    const body = $('#grid-body', root);
    const more = $('#grid-more', body);
    if (more) more.remove();
    body.insertAdjacentHTML('beforeend', state.items.slice(from, shown).map((c, j) => rowHtml(c, from + j)).join('') + moreHtml());
    bindRows($$('#grid-body tr[data-case]', root).slice(from));
    watchMore();
  }

  function watchMore() {
    if (!moreObserver) moreObserver = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) appendRows();
    }, { rootMargin: '400px' });
    moreObserver.disconnect();
    const more = $('#grid-more', root);
    if (more) moreObserver.observe(more);
  }

  // 저장 실패 시 그 행만 서버 값으로 다시 그린다
  function rerenderRow(id) {
    const i = state.items.findIndex((c) => c.case_id === id);
    const tr = $(`#grid-body tr[data-case="${CSS.escape(id)}"]`, root);
    if (i < 0 || !tr) return;
    tr.insertAdjacentHTML('afterend', rowHtml(state.items[i], i));
    const fresh = tr.nextElementSibling;
    tr.remove();
    bindRows([fresh]);
  }

  function bindRows(trs) {
    trs.forEach((tr) => {
      const id = tr.dataset.case;
      $('[data-id="grid-row-check"]', tr).addEventListener('change', (e) => {
        if (e.target.checked) state.selected.add(id); else state.selected.delete(id);
        tr.classList.toggle('sel', e.target.checked);
        updateBulk();
      });
      tr.addEventListener('click', (e) => {
        if (e.target.closest('input,select,.cell[contenteditable="true"],.drag')) return;
        NS.detail.open(id);
      });
      $('.drag', tr).addEventListener('dragstart', (e) => e.dataTransfer.setData('text/case', id));
      $('[data-id="grid-cell-priority"]', tr).addEventListener('change', (e) => save(id, { priority: e.target.value }));
      $('[data-id="grid-result"]', tr).addEventListener('change', (e) => save(id, { execution_result: e.target.value }));
      $$('[data-platform]', tr).forEach((select) => select.addEventListener('change', (e) => {
        const c = byId(id);
        save(id, { results: { ...(c.results || {}), [e.target.dataset.platform]: e.target.value } });
      }));
      $$('.cell[data-edit]', tr).forEach(bindCell);
    });
  }

  function bindCell(cell) {
    const start = () => {
      if (cell.isContentEditable) return;
      cell.dataset.orig = cell.innerText;
      cell.contentEditable = 'true';
      cell.focus();
    };
    cell.addEventListener('dblclick', start);
    cell.addEventListener('keydown', (e) => {
      if (!cell.isContentEditable) { if (e.key === 'Enter') { e.preventDefault(); start(); } return; }
      if (e.key === 'Escape') { cell.innerText = cell.dataset.orig; cell.contentEditable = 'false'; cell.classList.remove('bad'); }
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commitCell(cell); }
    });
    cell.addEventListener('blur', () => { if (cell.isContentEditable) commitCell(cell); });
  }

  function commitCell(cell) {
    const id = cell.closest('tr').dataset.case;
    const field = cell.dataset.edit;
    const value = cell.innerText.trim();
    cell.contentEditable = 'false';
    if (value === (cell.dataset.orig || '').trim()) return;
    if (field === 'steps') {
      const lines = value.split('\n').filter(Boolean);
      if (!lines.every((l) => /^\d+\.\s/.test(l))) {
        cell.classList.add('bad');
        toast('Test Step은 줄마다 "1. …" 형식이어야 합니다. 번호를 붙여 다시 저장하세요.', 'err');
        return;
      }
      cell.classList.remove('bad');
      save(id, { steps: lines.map((l) => l.replace(/^\d+\.\s*/, '')) }, cell);
      return;
    }
    if (field === 'expected') {
      const [head, ...rest] = value.split('\n');
      const bullets = rest.filter((x) => x.startsWith('-')).map((x) => ({
        text: x.replace(/^-\s*/, '').replace(/ \(추정\)$/, ''), verified: !x.includes('(추정)') }));
      save(id, { expected: head, bullets }, cell);
      return;
    }
    save(id, { [field]: value }, cell);
  }

  // 목업 saveField 대체: PATCH + 409 충돌 토스트 (명세 1.2 / F5.2)
  async function save(id, changes, el) {
    const c = byId(id);
    if (!c) return;
    if (el) el.classList.add('saving');
    try {
      const { case: updated } = await api.patchCase(state.suite, id, c.rev, changes);
      Object.assign(c, updated);
      toast(`${id} 저장됨 · rev ${updated.rev}`, 'ok', [], 1800);
      await refreshTreeOnly();
      renderGrid({ keep: true });
      NS.detail.refreshIfOpen();
    } catch (err) {
      if (err.status !== 409) {
        rerenderRow(id);   // 화면에 바꾼 값이 남아 서버 값과 달라 보이지 않게
        toast(`${id} 저장 실패: ${esc(err.message)}`, 'err', [{ id: 'toast-save-retry', label: '다시 시도', fn: () => save(id, changes) }], 0);
        return;
      }
      toast(`<b>${id}</b>를 저장하지 못했습니다. 다른 곳에서 먼저 바뀌었습니다 (내 rev ${c.rev}, 서버 rev ${err.data.server_case.rev}). 변경 내용은 그대로 남아 있습니다.`, 'err', [
        { id: 'toast-conflict-compare', label: '차이 비교', fn: () => NS.detail.open(id, 'history') },
        { id: 'toast-conflict-reload', label: '최신 값 불러오기', fn: () => reloadList() },
      ], 0);
    } finally {
      if (el) el.classList.remove('saving');
    }
  }
  NS.library.save = save;

  async function refreshTreeOnly() {
    state.tree = (await api.tree(state.suite)).tree;
    renderTree();
  }

  // ── 일괄 편집 (목업 updateBulk·bulk 이식) ─────────────────────
  function updateBulk() {
    const n = state.selected.size;
    $('#bulkbar', root).hidden = n < 1;
    $('#bulk-n', root).textContent = n;
    $('#grid-check-all', root).checked = n > 0 && state.items.every((c) => state.selected.has(c.case_id));
  }
  const selectedItems = () => state.items.filter((c) => state.selected.has(c.case_id))
    .map((c) => ({ case_id: c.case_id, rev: c.rev }));

  async function bulkSet(field, value, label) {
    const res = await api.bulk(state.suite, selectedItems(), 'set', field, value);
    const imported = (res.skipped || []).length;
    const skipped = (res.conflicts.length ? ` · ${res.conflicts.length}건은 다른 곳에서 바뀌어 건너뜀` : '')
      + (imported ? ` · ${imported}건은 가져온 케이스라 건너뜀` : '');
    toast(`${res.updated.length}건의 ${label}을(를) 바꿨습니다${skipped}`, res.conflicts.length || imported ? 'warn' : 'ok');
    await refresh();
  }

  function askDelete(ids) {
    $('#cf-title', root).textContent = `케이스 ${ids.length}건을 삭제할까요?`;
    $('#confirm-modal', root).hidden = false;
    $('#cf-ok', root).onclick = async () => {
      $('#confirm-modal', root).hidden = true;
      const items = state.items.filter((c) => ids.includes(c.case_id)).map((c) => ({ case_id: c.case_id, rev: c.rev }));
      const res = await api.bulk(state.suite, items, 'delete');
      ids.forEach((id) => state.selected.delete(id));
      if (ids.includes(state.activeId)) NS.detail.close({ force: true });
      toast(`${res.deleted.length}건을 삭제했습니다.`, 'ok', [{
        id: 'delete-undo', label: '되돌리기',
        fn: async () => { for (const id of res.deleted) await api.restore(state.suite, id); await refresh(); },
      }]);
      await refresh();
    };
  }
  NS.library.askDelete = askDelete;

  function openMove(ids) {
    const targets = [];
    const walk = (nodes) => nodes.forEach((n) => {
      if (n.level !== 'feature') { targets.push(n.path); walk(n.children || []); }
    });
    walk(state.tree);
    $('#move-target', root).innerHTML = targets.filter((p) => p.length >= 2)
      .map((p) => `<option value="${esc(p.join('/'))}">${esc(p.join(' › '))}</option>`).join('');
    $('#move-feature', root).value = '';
    $('#move-modal', root).hidden = false;
    $('#move-confirm', root).onclick = async () => {
      $('#move-modal', root).hidden = true;
      await moveCases(ids, $('#move-target', root).value.split('/'), $('#move-feature', root).value.trim());
    };
  }
  NS.library.openMove = openMove;

  async function moveCases(ids, target, feature) {
    const items = state.items.filter((c) => ids.includes(c.case_id)).map((c) => ({ case_id: c.case_id, rev: c.rev }));
    const [sheet, ...path] = target;
    const res = await api.move(state.suite, items, sheet, path.slice(0, 3), feature || undefined);
    toast(`${res.moved.length}건을 ${esc(target.join(' › '))}(으)로 옮겼습니다.`, res.conflicts.length ? 'warn' : 'ok');
    await refresh();
  }

  async function addCase() {
    const btn = $('#btn-add-case', root);
    if (btn.disabled) return;
    btn.disabled = true;          // 연타해도 1건만 만든다
    try {
      if (!(await NS.detail.confirmLeave())) return;
      const base = byId(state.activeId) || state.items[0];
      const fields = base
        ? { sheet: base.sheet, path: base.path, feature: '새 제목', after: base.case_id }
        : { feature: '새 제목' };
      const { case: created } = await api.createCase(state.suite, fields);
      await refresh();
      await NS.detail.open(created.case_id);
    } catch (err) {
      toast(`케이스를 추가하지 못했습니다: ${esc(err.message)}`, 'err');
    } finally {
      btn.disabled = false;
    }
  }

  function setTreeHidden(hidden) {
    $('#lib', root).classList.toggle('tree-hidden', hidden);
    const btn = $('#tree-toggle', root);
    btn.setAttribute('aria-pressed', hidden);
    btn.textContent = hidden ? '트리 보기' : '트리 숨기기';
    try { localStorage.setItem(TREE_KEY, hidden ? '1' : ''); } catch (e) { /* 저장 불가 환경 */ }
  }

  // ── 이벤트 연결 ──────────────────────────────────────────────
  function mount(r) {
    root = r;
    $('#grid-extra-columns', root).addEventListener('click', (e) => {
      const expanded = $('#grid', root).classList.toggle('show-extra-columns');
      e.currentTarget.setAttribute('aria-pressed', expanded);
      e.currentTarget.textContent = expanded ? '추가 열 숨기기' : '추가 열 보기';
    });
    const onFilter = (id, k, map = (v) => v) => $(id, root).addEventListener('change', (e) => {
      state.filters[k] = map(e.target.value);
      reloadList();
    });
    onFilter('#lib-filter-result', 'execution_result');
    onFilter('#lib-filter-platform', 'platform');
    $('#lib-filter-mismatch', root).addEventListener('click', (e) => {
      state.filters.mismatch = !state.filters.mismatch;
      e.currentTarget.setAttribute('aria-pressed', state.filters.mismatch);
      reloadList();
    });
    onFilter('#lib-filter-status', 'status');
    onFilter('#lib-filter-priority', 'priority');
    onFilter('#lib-filter-source', 'source');
    let t;
    $('#lib-search', root).addEventListener('input', (e) => {
      clearTimeout(t);
      t = setTimeout(() => { state.filters.q = e.target.value.trim(); reloadList(); }, 250);
    });
    if (NS.sourceWatch) {
      $('#lib-filter-needs-review', root).addEventListener('click', (e) => {
        const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
        e.currentTarget.setAttribute('aria-pressed', on);
        state.filters.needs_review = on;
        reloadList();
      });
      $('#btn-check-sources', root).addEventListener('click', () => NS.sourceWatch.scan(root));
    }
    $('#lib-filter-invalid', root).addEventListener('click', (e) => {
      const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
      e.currentTarget.setAttribute('aria-pressed', on);
      state.filters.invalid = on;
      reloadList();
    });
    $('#lib-filter-reset', root).addEventListener('click', () => {
      Object.keys(state.filters).forEach((k) => { state.filters[k] = ['invalid', 'needs_review', 'mismatch'].includes(k) ? false : ''; });
      $$('.fchip', root).forEach((b) => b.setAttribute('aria-pressed', 'false'));
      $$('.filterbar select', root).forEach((s) => { s.value = ''; });
      $('#lib-search', root).value = '';
      $('#lib-filter-invalid', root).setAttribute('aria-pressed', 'false');
      renderTree();
      reloadList();
    });
    $('#tree-search', root).addEventListener('input', renderTree);
    $('#tree-collapse-all', root).addEventListener('click', () => { open.clear(); renderTree(); });
    $('#grid-check-all', root).addEventListener('change', (e) => {
      state.items.forEach((c) => (e.target.checked ? state.selected.add(c.case_id) : state.selected.delete(c.case_id)));
      renderGrid({ keep: true });
    });
    const bulkSelect = (id, field, label, map = (v) => v) => $(id, root).addEventListener('change', async (e) => {
      const v = e.target.value;
      e.target.value = '';
      if (v) await bulkSet(field, map(v), label);
    });
    bulkSelect('#bulk-priority', 'priority', '우선순위');
    $('#bulk-result', root).addEventListener('change', async (e) => {
      const v = e.target.value;
      e.target.value = '';
      if (!v) return;
      const value = v === 'none' ? '' : v;
      if (NS.isAppSuite()) {
        const platform = $('#bulk-platform', root).value;
        await bulkSet('platform_result', { platform, result: value }, `${platform} 실행 결과`);
      } else {
        await bulkSet('execution_result', value, '실행 결과');
      }
    });
    bulkSelect('#bulk-status', 'status', '검토 상태');
    $('#bulk-clear', root).addEventListener('click', () => { state.selected.clear(); renderGrid({ keep: true }); });
    $('#bulk-move', root).addEventListener('click', () => openMove([...state.selected]));
    $('#bulk-delete', root).addEventListener('click', () => askDelete([...state.selected]));
    $('#bulk-duplicate', root).addEventListener('click', async () => {
      for (const id of state.selected) await api.duplicate(state.suite, id);
      toast(`${state.selected.size}건을 복제했습니다. 새 case_id가 붙고 초안 상태로 들어갑니다.`, 'ok');
      await refresh();
    });
    ['#move-close', '#move-cancel'].forEach((s) => $(s, root).addEventListener('click', () => { $('#move-modal', root).hidden = true; }));
    $('#cf-cancel', root).addEventListener('click', () => { $('#confirm-modal', root).hidden = true; });
    $('#btn-add-case', root).addEventListener('click', addCase);
    $('#tree-toggle', root).addEventListener('click', () => setTreeHidden(!$('#lib', root).classList.contains('tree-hidden')));
    let treeHidden = false;
    try { treeHidden = localStorage.getItem(TREE_KEY) === '1'; } catch (e) { /* 저장 불가 환경 */ }
    setTreeHidden(treeHidden);
    if (NS.importModal) $('#empty-import-xlsx', root).addEventListener('click', () => NS.importModal.open());
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') $$('.scrim', root).forEach((s) => {
        if (s.hidden || s.id === 'import-modal') return;
        if (s.id === 'dirty-modal') $('#dirty-cancel', root).click();   // 약속(Promise)을 끝내야 하므로 닫기만 하지 않는다
        else s.hidden = true;
      });
      if (e.key === '/' && state.screen === 'library' && !e.target.closest('input,textarea,[contenteditable="true"]')) {
        e.preventDefault();
        $('#lib-search', root).focus();
      }
    });
    NS.detail.mount(root);
  }
})(window.TCS_NS = window.TCS_NS || {});
