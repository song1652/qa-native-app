// TC 스튜디오 — 케이스 상세 패널: 편집·Step 순서·UI 문구·검증·이력·되돌리기 (PRD F5.2, F5.8, F5.11)
(function (NS) {
  'use strict';

  const { state, api, esc, $, $$, toast } = NS;
  let root = null;
  let current = null;   // 서버에서 받은 케이스 (rev 기준)
  let draft = null;     // 편집 중인 사본

  NS.detail = { html, mount, open, close, refreshIfOpen, confirmLeave };

  const opt = (v, label) => `<option value="${esc(v)}">${esc(label)}</option>`;

  function html() {
    return `
      <aside class="detail" id="detail" data-id="detail-panel" aria-label="케이스 상세">
        <div class="detail-head">
          <div class="row">
            <span class="mono faint" id="d-id"></span><span id="d-status"></span>
            <span id="d-rev" class="mono faint" style="font-size:10.5px"></span><span class="spacer"></span>
            <span id="d-dirty" hidden title="저장하지 않은 변경"><i class="dirty-dot"></i></span>
            <button class="icon-btn" data-id="detail-close" id="detail-close" aria-label="패널 닫기">✕</button>
          </div>
          <input class="input" id="detail-feature" data-id="detail-feature" style="font-weight:600;font-size:14px" aria-label="제목">
          <div class="row" style="font-size:11.5px"><span class="faint">경로</span><span id="d-path" class="crumbpath"></span>
            <button class="btn-sm" data-id="detail-move" id="detail-move">이동…</button></div>
        </div>
        <div class="detail-tabs" role="tablist">
          <button class="dtab" role="tab" data-id="detail-tab-edit" data-pane="edit" aria-selected="true">편집</button>
          <button class="dtab" role="tab" data-id="detail-tab-source" data-pane="source" aria-selected="false">원문</button>
          <button class="dtab" role="tab" data-id="detail-tab-history" data-pane="history" aria-selected="false">이력</button>
        </div>
        <div class="detail-body">
          <div class="dpane active" data-pane="edit">
            <div class="two">
              <div class="field"><span class="label">우선순위</span><select class="select" id="detail-priority" data-id="detail-priority">${opt('', '미지정')}${NS.PRIORITIES.map((p) => opt(p, p)).join('')}</select></div>
              <div class="field web-result"><span class="label">실행 결과</span><select class="select" id="detail-result" data-id="detail-result">${Object.entries(NS.RESULT_LABEL).map(([k, l]) => opt(k, l)).join('')}</select></div>
              <div class="field app-only"><span class="label">대상 플랫폼</span><div class="row"><label><input type="checkbox" id="detail-platform-android"> And</label><label><input type="checkbox" id="detail-platform-ios"> iOS</label></div></div>
              <div class="field app-only"><span class="label">And 결과</span><select class="select" id="detail-result-android">${Object.entries(NS.RESULT_LABEL).map(([k, l]) => opt(k, l)).join('')}</select></div>
              <div class="field app-only"><span class="label">iOS 결과</span><select class="select" id="detail-result-ios">${Object.entries(NS.RESULT_LABEL).map(([k, l]) => opt(k, l)).join('')}</select></div>
              <div class="field"><span class="label">검토 상태</span><select class="select" id="detail-status" data-id="detail-status">${Object.entries(NS.STATUS_LABEL).map(([k, l]) => opt(k, l)).join('')}</select></div>
            </div>
            <div class="field"><label class="label" for="detail-source-tc-id">원본 TC ID</label><input class="input mono" id="detail-source-tc-id" data-id="detail-source-tc-id" readonly></div>
            <div class="field"><label class="label" for="detail-tags">태그</label><input class="input" id="detail-tags" data-id="detail-tags" placeholder="쉼표로 구분"><span class="help">태그를 쉼표로 구분해 입력하세요.</span></div>
            <div class="field"><label class="label" for="detail-precondition">사전 조건</label><textarea class="textarea" id="detail-precondition" data-id="detail-precondition" rows="2"></textarea></div>
            <div class="field">
              <div class="row"><span class="label">테스트 단계</span><span class="spacer"></span><span class="faint" style="font-size:10.5px">끌어서 순서 변경 · <span class="kbd">Alt</span><span class="kbd">↑↓</span></span></div>
              <ol class="steps" id="d-steps" data-id="detail-steps"></ol>
              <button class="btn-sm" data-id="detail-step-add" id="detail-step-add" style="justify-self:start">+ 단계 추가</button>
            </div>
            <div class="field"><label class="label" for="detail-expected">기대 결과</label>
              <textarea class="textarea" id="detail-expected" data-id="detail-expected" rows="2"></textarea><span class="help" id="d-exp-help"></span></div>
            <div class="field">
              <div class="row"><span class="label">UI 문구</span><span class="spacer"></span><span class="faint" style="font-size:10.5px">배지를 눌러 확인/추정 전환</span></div>
              <div class="bullets" id="d-bullets" data-id="detail-bullets"></div>
              <button class="btn-sm" data-id="detail-bullet-add" id="detail-bullet-add" style="justify-self:start">+ 문구 추가</button>
            </div>
            <div class="field"><label class="label" for="detail-note">메모 (기타)</label><textarea class="textarea" id="detail-note" data-id="detail-note" rows="2"></textarea></div>
            <div class="field"><span class="label">출처 (source_refs)</span><div class="row" id="d-refs"></div></div>
            <div class="field"><span class="label">검증</span><ul class="checks" id="d-checks" data-id="detail-validation"></ul></div>
          </div>
          <div class="dpane" data-pane="source" id="d-source"></div>
          <div class="dpane" data-pane="history"><ul class="hist" id="d-hist" data-id="detail-history"></ul></div>
        </div>
        <div class="detail-foot">
          <button class="btn btn-primary" data-id="detail-save" id="detail-save" disabled>저장</button>
          <button class="btn btn-ghost" data-id="detail-revert-edits" id="detail-revert-edits" disabled>변경 취소</button>
          <span class="spacer"></span>
          <button class="btn-sm" data-id="detail-duplicate" id="detail-duplicate">복제</button>
          <button class="btn btn-danger" data-id="detail-delete" id="detail-delete" style="padding:4px 10px;font-size:11px">삭제</button>
        </div>
      </aside>`;
  }

  // 다른 케이스·스위트로 옮기기 전에 저장하지 않은 변경을 묻는다. true면 진행해도 된다
  function confirmLeave() {
    if (!isDirty()) return Promise.resolve(true);
    const modal = $('#dirty-modal', root);
    $('#dirty-title', root).textContent = `${current.case_id}에 저장하지 않은 변경이 있습니다`;
    modal.hidden = false;
    $('#dirty-save', root).focus();
    return new Promise((resolve) => {
      const done = (ok) => { modal.hidden = true; resolve(ok); };
      $('#dirty-cancel', root).onclick = () => done(false);
      $('#dirty-discard', root).onclick = () => { draft = JSON.parse(JSON.stringify(current)); fill(); done(true); };
      $('#dirty-save', root).onclick = async () => { modal.hidden = true; resolve(await saveDetail()); };
    });
  }

  async function open(caseId, tab = 'edit') {
    // 같은 케이스를 다시 여는 것(저장 뒤·"최신 값 불러오기")은 묻지 않는다
    if (current && current.case_id !== caseId && !(await confirmLeave())) return;
    state.activeId = caseId;
    const { case: c } = await api.getCase(state.suite, caseId);
    current = c;
    draft = JSON.parse(JSON.stringify(c));
    $('#lib', root).classList.remove('no-detail');
    $$('#grid-body tr', root).forEach((tr) => tr.classList.toggle('active', tr.dataset.case === caseId));
    fill();
    selectTab(tab);
  }

  async function close({ force = false } = {}) {
    if (!force && !(await confirmLeave())) return;
    state.activeId = '';
    current = draft = null;
    $('#lib', root).classList.add('no-detail');
    $$('#grid-body tr.active', root).forEach((tr) => tr.classList.remove('active'));
  }

  async function refreshIfOpen() {
    if (!state.activeId || isDirty()) return;
    const still = state.items.some((c) => c.case_id === state.activeId);
    if (still) await open(state.activeId, currentTab());
  }

  const isDirty = () => current && draft && JSON.stringify(pick(current)) !== JSON.stringify(pick(draft));
  const pick = (c) => ({ feature: c.feature, precondition: c.precondition, steps: c.steps, expected: c.expected,
    bullets: c.bullets, priority: c.priority, execution_result: c.execution_result,
    platforms: c.platforms, results: c.results,
    status: c.status, note: c.note, tags: c.tags || [] });
  const currentTab = () => ($('.dtab[aria-selected="true"]', root) || {}).dataset?.pane || 'edit';

  function markDirty() {
    const dirty = isDirty();
    $('#d-dirty', root).hidden = !dirty;
    $('#detail-save', root).disabled = !dirty;
    $('#detail-revert-edits', root).disabled = !dirty;
  }

  function fill() {
    const c = draft;
    $('#d-id', root).textContent = c.case_id;
    const imported = NS.isImported(current);
    $('#d-status', root).innerHTML = (imported
      ? `<span class="pill st-imported" data-id="detail-imported" title="${esc(NS.importedTitle(current))}">가져옴</span>`
      : `<span class="pill st-${current.status}">${NS.STATUS_LABEL[current.status]}</span>`)
      + ((current.flags || {}).source_change ? ' <span class="pill st-needs_review">재검토 필요</span>' : '');
    $('#d-rev', root).textContent = `rev ${current.rev}`;
    $('#detail-feature', root).value = c.feature;
    $('#d-path', root).textContent = [c.sheet, ...c.path.filter(Boolean)].join(' › ');
    $('#detail-priority', root).value = c.priority;
    $('#detail-result', root).value = c.execution_result;
    ['android', 'ios'].forEach((platform) => {
      const included = (c.platforms || ['android', 'ios']).includes(platform);
      $(`#detail-platform-${platform}`, root).checked = included;
      $(`#detail-result-${platform}`, root).value = included ? (c.results || {})[platform] || '' : 'na';
      $(`#detail-result-${platform}`, root).disabled = !included;
    });
    $('#detail-status', root).value = c.status;
    $('#detail-status', root).disabled = imported;
    $('#detail-status', root).title = imported ? NS.importedTitle(current) : '';
    $('#detail-precondition', root).value = c.precondition;
    $('#detail-expected', root).value = c.expected;
    $('#detail-note', root).value = c.note;
    $('#detail-source-tc-id', root).value = c.source_tc_id || '';
    $('#detail-tags', root).value = (c.tags || []).join(', ');
    const vague = /정상\s*동작|정상적으로\s*노출/.test(c.expected);
    $('#d-exp-help', root).textContent = vague ? '모호한 표현이 있습니다. 화면에 보이는 결과를 구체적으로 적어 주세요.' : '';
    $('#d-exp-help', root).className = 'help' + (vague ? ' err' : '');
    renderSteps();
    renderBullets();
    $('#d-refs', root).innerHTML = c.source_refs.map((r) => `<span class="src-ref">${esc(r)}</span>`).join('');
    $('#d-checks', root).innerHTML = (current.issues.length ? current.issues : [{ level: 'ok', message: '문제 없음' }])
      .map((i) => `<li><span class="${i.level === 'error' ? 'bad' : i.level === 'warning' ? 'wr' : 'ok'}">${i.level === 'error' ? '✕' : i.level === 'warning' ? '!' : '✓'}</span>${esc(i.message)}</li>`).join('');
    $('#d-source', root).innerHTML = `<div class="excerpt"><h5>출처</h5>${c.source_refs.map((r) => `<div class="mono" style="font-size:11px">${esc(r)}</div>`).join('')}
      <p class="faint" style="margin:8px 0 0">문서 원문 하이라이트는 초안 검토 화면에서 봅니다. 엑셀에서 온 케이스는 가져온 파일·시트·행을 보여줍니다.</p></div>`;
    if (NS.sourceWatch) {
      NS.sourceWatch.detailSource($('#d-source', root), current, async () => {
        await api.ackSource(state.suite, current.case_id);
        toast(`${current.case_id}의 출처를 새 버전으로 올리고 재검토를 해제했습니다.`, 'ok');
        await NS.library.refresh();
        await open(current.case_id, 'source');
      });
    }
    loadHistory();
    markDirty();
  }

  function renderSteps() {
    $('#d-steps', root).innerHTML = draft.steps.map((t, i) => `<li class="step" draggable="true" data-i="${i}">
      <span class="drag" data-id="detail-step-drag" aria-hidden="true">⋮⋮</span><span class="idx">${i + 1}.</span>
      <input value="${esc(t)}" data-id="detail-step-input" aria-label="Step ${i + 1}">
      <button class="icon-btn" data-id="detail-step-remove" aria-label="Step ${i + 1} 삭제">✕</button></li>`).join('');
    let from = null;
    $$('#d-steps .step', root).forEach((li) => {
      const i = +li.dataset.i;
      const input = $('input', li);
      input.addEventListener('input', () => { draft.steps[i] = input.value; markDirty(); });
      input.addEventListener('keydown', (e) => {
        if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
          e.preventDefault();
          const j = i + (e.key === 'ArrowUp' ? -1 : 1);
          if (j < 0 || j >= draft.steps.length) return;
          [draft.steps[i], draft.steps[j]] = [draft.steps[j], draft.steps[i]];
          renderSteps(); markDirty();
          $$('#d-steps input', root)[j].focus();
        }
        if (e.key === 'Enter') {
          e.preventDefault();
          draft.steps.splice(i + 1, 0, '');
          renderSteps(); markDirty();
          $$('#d-steps input', root)[i + 1].focus();
        }
      });
      $('[data-id="detail-step-remove"]', li).addEventListener('click', () => { draft.steps.splice(i, 1); renderSteps(); markDirty(); });
      li.addEventListener('dragstart', () => { from = i; li.classList.add('dragging'); });
      li.addEventListener('dragend', () => li.classList.remove('dragging'));
      li.addEventListener('dragover', (e) => { e.preventDefault(); li.classList.add('over'); });
      li.addEventListener('dragleave', () => li.classList.remove('over'));
      li.addEventListener('drop', (e) => {
        e.preventDefault();
        const [moved] = draft.steps.splice(from, 1);
        draft.steps.splice(i, 0, moved);
        renderSteps(); markDirty();
      });
    });
  }

  function renderBullets() {
    $('#d-bullets', root).innerHTML = draft.bullets.map((b, i) => `<div class="bullet" data-i="${i}">
      <button class="vtoggle tag ${b.verified ? 'ok' : 'warn'}" data-id="detail-bullet-verify" title="${b.verified ? 'Figma·실서비스에서 확인한 문구' : 'PRD에만 있는 문구. md 내보내기에서 제외됩니다'}">${b.verified ? '확인' : '추정'}</button>
      <input value="${esc(b.text)}" data-id="detail-bullet-input" aria-label="UI 문구 ${i + 1}">
      <button class="icon-btn" data-id="detail-bullet-remove" aria-label="문구 삭제">✕</button></div>`).join('')
      || '<span class="help">UI 문구가 없습니다</span>';
    $$('#d-bullets .bullet', root).forEach((el) => {
      const i = +el.dataset.i;
      $('[data-id="detail-bullet-verify"]', el).addEventListener('click', () => { draft.bullets[i].verified = !draft.bullets[i].verified; renderBullets(); markDirty(); });
      $('input', el).addEventListener('input', (e) => { draft.bullets[i].text = e.target.value; markDirty(); });
      $('[data-id="detail-bullet-remove"]', el).addEventListener('click', () => { draft.bullets.splice(i, 1); renderBullets(); markDirty(); });
    });
  }

  async function loadHistory() {
    const caseId = draft.case_id;
    const { history } = await api.history(state.suite, caseId);
    if (!draft || draft.case_id !== caseId) return;
    const fmt = (v) => esc(typeof v === 'string' ? v : JSON.stringify(v));
    $('#d-hist', root).innerHTML = history.map((e) => `<li><span class="when">${esc(e.at.replace('T', ' ').slice(5, 16))}</span>
      <div><b>${esc(e.kind === 'edit' ? e.field : e.kind)}</b> · <span class="faint">${esc(e.actor)}</span>
        ${e.kind === 'edit' ? `<div class="diff"><del>${fmt(e.before) || '—'}</del> <ins>${fmt(e.after) || '—'}</ins></div>` : ''}</div>
      ${e.kind === 'edit' ? `<button class="btn-sm" data-id="detail-history-revert" data-h="${e.history_id}">되돌리기</button>` : '<span></span>'}</li>`).join('')
      || '<li class="faint">이력이 없습니다</li>';
    $$('[data-id="detail-history-revert"]', root).forEach((b) => b.addEventListener('click', async () => {
      try {
        await api.revert(state.suite, caseId, b.dataset.h, current.rev);
        toast('이전 값으로 되돌렸습니다. 되돌린 것도 이력에 남습니다.', 'ok');
        await NS.library.reloadList();
        await open(caseId, 'history');
      } catch (err) {
        toast(err.status === 409 ? '다른 곳에서 먼저 바뀌었습니다. 최신 값을 불러온 뒤 다시 시도하세요.' : esc(err.message), 'err');
      }
    }));
  }

  function selectTab(p) {
    $$('.dtab', root).forEach((t) => t.setAttribute('aria-selected', t.dataset.pane === p));
    $$('.dpane', root).forEach((d) => d.classList.toggle('active', d.dataset.pane === p));
  }

  // 성공하면 true (저장하고 이동할 때 결과를 본다)
  async function saveDetail() {
    if (draft.steps.some((s) => !s.trim())) { toast('빈 Step이 있습니다. 내용을 쓰거나 지우고 저장하세요.', 'err'); return false; }
    const changes = {};
    Object.entries(pick(draft)).forEach(([k, v]) => {
      if (JSON.stringify(v) !== JSON.stringify(current[k])) changes[k] = v;
    });
    const btn = $('#detail-save', root);
    btn.classList.add('loading');
    btn.disabled = true;
    try {
      const { case: saved } = await api.patchCase(state.suite, current.case_id, current.rev, changes);
      toast(`${saved.case_id} 저장됨 · rev ${saved.rev}`, 'ok', [], 1800);
      current = null;
      await NS.library.refresh();
      await open(saved.case_id, currentTab());
      return true;
    } catch (err) {
      btn.disabled = false;
      if (err.status === 409) {
        toast(`<b>${current.case_id}</b>를 저장하지 못했습니다. 다른 곳에서 먼저 바뀌었습니다 (내 rev ${current.rev}, 서버 rev ${err.data.server_case.rev}). 변경 내용은 그대로 남아 있습니다.`, 'err', [
          { id: 'toast-conflict-compare', label: '차이 비교', fn: () => selectTab('history') },
          { id: 'toast-conflict-reload', label: '최신 값 불러오기', fn: () => open(current.case_id) },
        ], 0);
      } else {
        toast(`저장 실패: ${esc(err.message)}`, 'err');
      }
      return false;
    } finally {
      btn.classList.remove('loading');
    }
  }

  function mount(r) {
    root = r;
    const bindField = (sel, field) => $(sel, root).addEventListener('input', (e) => { if (draft) { draft[field] = e.target.value; markDirty(); } });
    bindField('#detail-feature', 'feature');
    bindField('#detail-precondition', 'precondition');
    bindField('#detail-expected', 'expected');
    bindField('#detail-note', 'note');
    $('#detail-tags', root).addEventListener('input', (e) => {
      if (!draft) return;
      draft.tags = [...new Set(e.target.value.split(',').map((t) => t.trim()).filter(Boolean))];
      markDirty();
    });
    [['#detail-priority', 'priority'], ['#detail-result', 'execution_result'], ['#detail-status', 'status']]
      .forEach(([sel, field]) => $(sel, root).addEventListener('change', (e) => { draft[field] = e.target.value; markDirty(); }));
    ['android', 'ios'].forEach((platform) => {
      $(`#detail-platform-${platform}`, root).addEventListener('change', (e) => {
        const platforms = new Set(draft.platforms || ['android', 'ios']);
        if (e.target.checked) platforms.add(platform); else platforms.delete(platform);
        if (!platforms.size) { e.target.checked = true; return; }
        draft.platforms = ['android', 'ios'].filter((p) => platforms.has(p));
        draft.results = { ...(draft.results || {}), [platform]: e.target.checked ? '' : 'na' };
        fill(); markDirty();
      });
      $(`#detail-result-${platform}`, root).addEventListener('change', (e) => {
        draft.results = { ...(draft.results || {}), [platform]: e.target.value };
        markDirty();
      });
    });
    $('#detail-step-add', root).addEventListener('click', () => {
      draft.steps.push(''); renderSteps(); markDirty();
      $$('#d-steps input', root).at(-1).focus();
    });
    $('#detail-bullet-add', root).addEventListener('click', () => {
      draft.bullets.push({ text: '', verified: false }); renderBullets(); markDirty();
      $$('#d-bullets input', root).at(-1).focus();
    });
    $$('.dtab', root).forEach((t) => t.addEventListener('click', () => selectTab(t.dataset.pane)));
    $('#detail-close', root).addEventListener('click', () => close());
    window.addEventListener('beforeunload', (e) => {
      if (root && document.body.contains(root) && isDirty()) { e.preventDefault(); e.returnValue = ''; }
    });
    $('#detail-revert-edits', root).addEventListener('click', () => { draft = JSON.parse(JSON.stringify(current)); fill(); });
    $('#detail-save', root).addEventListener('click', saveDetail);
    $('#detail-move', root).addEventListener('click', () => NS.library.openMove([state.activeId]));
    $('#detail-delete', root).addEventListener('click', () => NS.library.askDelete([state.activeId]));
    $('#detail-duplicate', root).addEventListener('click', async () => {
      const { case: dup } = await api.duplicate(state.suite, state.activeId);
      toast(`${state.activeId}를 복제했습니다 → ${dup.case_id} (초안)`, 'ok');
      await NS.library.refresh();
      await open(dup.case_id);
    });
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's' && state.screen === 'library' && state.activeId) {
        e.preventDefault();
        if (!$('#detail-save', root).disabled) saveDetail();
      }
    });
  }
})(window.TCS_NS = window.TCS_NS || {});
