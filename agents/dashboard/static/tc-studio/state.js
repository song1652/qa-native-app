// TC 스튜디오 — 화면 상태와 공용 도우미
(function (NS) {
  'use strict';

  NS.state = {
    suites: [],
    suite: '',
    tree: [],
    items: [],          // 현재 필터 결과 (서버 응답 그대로, issues 포함)
    total: 0,
    filters: { q: '', path: '', status: '', execution_result: '', platform: '', mismatch: false, priority: '',
               source: '', invalid: false, needs_review: false },
    selected: new Set(),
    activeId: '',
    screen: 'library',
    lastUndo: null,     // { label, run: async () => {} }
  };

  NS.STATUS_LABEL = { draft: '초안', approved: '승인', rejected: '반려', needs_review: '재검토 필요' };
  // 엑셀에서 가져와 자동 승인된 케이스 — 검토 대상이 아니라 검토 상태를 바꿀 수 없다
  NS.isImported = (c) => c.review_source === 'import';
  NS.importedTitle = (c) => `엑셀에서 가져온 케이스는 검토 상태를 바꿀 수 없습니다${c.import_origin && c.import_origin.filename ? ` (출처: ${c.import_origin.filename.replace(/^xlsx:/, '')})` : ''}`;
  NS.RESULT_LABEL = { '': '미실행', pass: '통과', fail: '실패', not_test: '미실행', na: 'N/A' };
  NS.PRIORITIES = ['P0', 'P1', 'P2', 'P3'];
  NS.isAppSuite = () => (NS.state.suites.find((s) => s.suite === NS.state.suite) || {}).kind === 'app';

  // 필터 → GET /api/tc-library/{suite} 쿼리. 실행 결과 "none" = 미실행(빈 값).
  NS.queryFromFilters = function (f) {
    const q = {};
    Object.entries(f).forEach(([k, v]) => {
      if (k === 'invalid' || k === 'needs_review' || k === 'mismatch') { if (v) q[k] = '1'; return; }
      if (k === 'execution_result') {
        if (v === 'none') q.execution_result = '';
        else if (v) q.execution_result = v;
        return;
      }
      if (v) q[k] = v;
    });
    return q;
  };

  NS.esc = function (s) {
    return String(s ?? '').replace(/[&<>"]/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  };

  NS.$ = (sel, root = document) => root.querySelector(sel);
  NS.$$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // 목업 toast() 이식. actions: [{ id, label, fn }]
  NS.toast = function (msg, kind = '', actions = [], ms = 3800) {
    const box = NS.$('#tcs-toasts');
    if (!box) return null;
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    el.innerHTML = `<div>${msg}</div>` + (actions.length
      ? `<div class="row">${actions.map((a, i) =>
        `<button class="btn-sm" data-id="${a.id}" data-i="${i}">${NS.esc(a.label)}</button>`).join('')}</div>`
      : '');
    actions.forEach((a, i) => el.querySelector(`[data-i="${i}"]`).addEventListener('click', async () => {
      el.remove();
      if (a.fn) await a.fn();
    }));
    box.appendChild(el);
    if (ms) setTimeout(() => el.remove(), ms);
    return el;
  };
})(window.TCS_NS = window.TCS_NS || {});
