// TC 스튜디오 — 진입점: 셸 렌더, 스위트 선택, 화면 전환. 공개 API: window.TCS.init(selector)
// 화면 모듈(generateView·reviewView·exportView·importModal)은 스크립트가 로드된 것만 붙는다.
(function (NS) {
  'use strict';

  const { state, api, esc, $, $$ } = NS;
  const SUITE_KEY = 'tcs-suite';
  const DEFAULT_SUITE = '기본양식';
  const SCREENS = [
    { id: 'generate', label: '기획 정보 · 생성', module: 'generateView' },
    { id: 'library', label: '라이브러리', module: 'library', count: 'cnt-lib' },
    { id: 'review', label: '초안 검토', module: 'reviewView', count: 'cnt-review' },
    { id: 'export', label: '내보내기', module: 'exportView' },
  ];
  let root = null;
  let screenVersion = 0;

  const available = () => SCREENS.filter((s) => NS[s.module]);

  function navHtml() {
    return available().map((s, i) => `${i ? '<div class="step-line"></div>' : ''}<button class="step-item" role="tab" data-id="nav-tab-${s.id}" data-screen="${s.id}" aria-selected="false"><span class="step-circle">${i + 1}</span><span class="step-label">${s.label}</span>${s.count ? `<span class="step-count num" id="${s.count}">0</span>` : ''}</button>`).join('');
  }

  function shellHtml() {
    return `
<div class="tc-studio">
 <div class="studio" id="studio">
  <header class="page-header">
    <div class="ph-top">
      <h1 class="page-title">TC 스튜디오</h1>
      <label class="suite-label" for="suite-select">스위트</label><select class="suite-select" id="suite-select" data-id="suite-select" aria-label="스위트 선택"></select>
      <div class="suite-menu-wrap">
        <button class="icon-btn suite-menu-btn" type="button" id="suite-menu-btn" data-id="suite-menu-btn" aria-label="스위트 관리" aria-haspopup="menu" aria-expanded="false">⋯</button>
        <div class="suite-menu" id="suite-menu" data-id="suite-menu" role="menu" hidden>
          <button type="button" role="menuitem" class="danger" id="suite-menu-delete" data-id="suite-menu-delete">현재 스위트 삭제…</button>
          <button type="button" role="menuitem" id="suite-menu-trash" data-id="suite-menu-trash">삭제한 스위트 <span class="num" id="trash-n">0</span></button>
        </div>
      </div>
      <span class="spacer"></span>
      ${NS.importModal ? '<button class="btn btn-ghost" data-id="btn-import-xlsx" id="btn-import-xlsx">엑셀 가져오기</button>' : ''}
    </div>
    <nav class="wizard" role="tablist" aria-label="스튜디오 화면">${navHtml()}</nav>
  </header>
  ${available().map((s) => NS[s.module].html()).join('')}
  <div class="studio-loading" data-id="studio-loading" role="status">스위트를 불러오는 중…</div>
 </div>
 ${NS.importModal ? NS.importModal.html() : ''}
 <div class="scrim" id="suite-delete-modal" data-id="suite-delete-modal" hidden>
  <div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="sd-title" style="width:min(480px,100%)">
   <div class="panel-body" style="display:grid;gap:14px">
    <b id="sd-title" style="font-size:15px"></b>
    <div class="sd-summary" id="sd-summary" data-id="suite-delete-summary"></div>
    <ul class="sd-notes">
     <li>TC·엑셀 양식·변경 이력이 스위트 목록에서 사라집니다.</li>
     <li>삭제한 스위트는 <b id="sd-days">30</b>일 동안 보관되며, <b>⋯ › 삭제한 스위트</b>에서 복원할 수 있습니다.</li>
     <li>이미 파일로 내보낸 TC(testcases 폴더)와 원본 엑셀 파일은 그대로 남습니다.</li>
    </ul>
    <p class="help" style="margin:0">엑셀을 기존 스위트에 잘못 합쳐 넣은 거라면 스위트를 지우지 말고 <b>엑셀 가져오기 › 가져오기 이력</b>에서 그 작업만 되돌리세요.</p>
    <p class="help err" id="sd-block" data-id="suite-delete-block" style="margin:0" hidden></p>
    <div class="row"><button class="btn btn-ghost" type="button" id="sd-backup" data-id="suite-delete-backup">엑셀로 백업 먼저 받기</button><span class="spacer"></span>
     <button class="btn btn-ghost" type="button" id="sd-cancel" data-id="suite-delete-cancel">취소</button>
     <button class="btn btn-danger-solid" type="button" id="sd-ok" data-id="suite-delete-confirm">스위트 삭제</button></div>
   </div>
  </div>
 </div>
 <div class="scrim" id="trash-modal" data-id="trash-modal" hidden>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="tr-title" style="width:min(560px,100%)">
   <div class="panel-head"><span id="tr-title">삭제한 스위트</span><span class="faint" style="font-weight:400;font-size:11.5px" id="tr-help"></span><span class="spacer"></span><button class="icon-btn" type="button" id="tr-close" data-id="trash-close" aria-label="닫기">✕</button></div>
   <div class="panel-body"><ul class="trash-list" id="trash-list" data-id="trash-list"></ul></div>
  </div>
 </div>
 <div class="toasts" id="tcs-toasts" aria-live="polite"></div>
</div>`;
  }

  // auto: 스위트를 불러온 뒤 첫 화면을 고르는 자동 전환. screenVersion은 '사용자가 다른 화면으로 갔는가'를
  // 판단하는 값이라 자동 전환은 올리지 않는다 (올리면 뒤이어 고른 스위트가 화면 고르기를 포기한다)
  function show(screen, auto) {
    if (!auto) screenVersion++;
    state.screen = screen;
    $$('.step-item', root).forEach((b) => b.setAttribute('aria-selected', b.dataset.screen === screen));
    $$('.screen', root).forEach((s) => s.classList.toggle('active', s.dataset.screen === screen));
    const spec = SCREENS.find((s) => s.id === screen);
    if (spec && NS[spec.module].onShow) NS[spec.module].onShow();
  }
  NS.show = show;

  function renderSuiteSelect() {
    const sel = $('#suite-select', root);
    const ordered = [...state.suites].sort((a, b) =>
      Number(a.suite === '기본양식') - Number(b.suite === '기본양식'));
    sel.innerHTML = ordered.map((s) => `<option value="${esc(s.suite)}" ${s.suite === state.suite ? 'selected' : ''}>${esc(s.suite)} (${s.count})</option>`).join('')
      || '<option value="">스위트 없음</option>';
    sel.disabled = !state.suites.length;
    $('#gen-no-suite', root).hidden = !!state.suites.length;
    const cur = state.suites.find((s) => s.suite === state.suite);
    $('#cnt-lib', root).textContent = cur ? cur.count : 0;
  }

  // 케이스 추가·삭제·복제 뒤 스위트 선택 상자의 "(건수)"를 맞춘다 (선택한 스위트는 바꾸지 않는다)
  NS.refreshSuiteCounts = async function () {
    const { suites } = await api.suites();
    state.suites = suites;
    renderSuiteSelect();
  };

  NS.refreshCounts = async function () {
    const badge = $('#cnt-review', root);
    if (!badge || !state.suite) return;
    badge.textContent = (await api.list(state.suite, { status: 'draft', limit: 1 })).total;
  };

  // 가져오기 후에도 호출된다 (import.js)
  NS.reloadSuites = async function (prefer) {
    const previousSuite = state.suite;
    const navigationVersion = screenVersion;
    state.suites = (await api.suites()).suites;
    let saved = prefer || '';
    if (!saved) { try { saved = localStorage.getItem(SUITE_KEY) || ''; } catch (e) { saved = ''; } }
    state.suite = state.suites.some((s) => s.suite === saved) ? saved : (state.suites[0] ? state.suites[0].suite : '');
    root.classList.toggle('app-suite', NS.isAppSuite());
    try { if (state.suite) localStorage.setItem(SUITE_KEY, state.suite); } catch (e) { /* 저장 불가 환경 */ }
    renderSuiteSelect();
    state.selected.clear();
    const changed = previousSuite !== state.suite;
    if (changed) {
      Object.keys(state.filters).forEach((k) => { state.filters[k] = ['invalid', 'needs_review', 'mismatch'].includes(k) ? false : ''; });
      $$('.filterbar select, .filterbar input, #tree-search', root).forEach((el) => { el.value = ''; });
      $$('.filterbar .fchip', root).forEach((el) => el.setAttribute('aria-pressed', 'false'));
      NS.detail.close({ force: true });
      state.reviewJob = null;
    }
    await NS.library.refresh();
    await NS.refreshCounts();
    if (changed && NS.generateView) {
      const suite = state.suite;
      const context = suite ? await api.authoringContext(suite) : { job: null };
      if (state.suite !== suite) return;
      await NS.generateView.loadSuite(context.job, screenVersion !== navigationVersion);
      if (state.suite !== suite) return;
      const current = state.suites.find((s) => s.suite === suite);
      if (screenVersion === navigationVersion) show(current && current.count ? 'library' : 'generate', true);
    }
  };

  // ── 스위트 삭제·휴지통 ───────────────────────────────────────
  const ACTIVE_JOB = ['queued', 'fetching', 'drafting', 'validating'];
  const fmtTime = (iso) => (iso || '').replace('T', ' ').slice(5, 16);

  function toggleSuiteMenu(open) {
    const menu = $('#suite-menu', root);
    menu.hidden = !open;
    $('#suite-menu-btn', root).setAttribute('aria-expanded', open);
    if (open) {
      const isDefault = !!(state.suites.find((s) => s.suite === state.suite) || {}).protected;
      const del = $('#suite-menu-delete', root);
      del.disabled = !state.suite || isDefault;
      del.title = isDefault ? '기본 양식은 삭제할 수 없습니다' : '';
      api.trash().then(({ items }) => { $('#trash-n', root).textContent = items.length; }).catch(() => {});
    }
  }

  async function openSuiteDelete() {
    toggleSuiteMenu(false);
    if (!state.suite || !(await NS.detail.confirmLeave())) return;
    const suite = state.suite;
    const cur = state.suites.find((s) => s.suite === suite) || { count: 0, sheets: [] };
    $('#sd-title', root).innerHTML = `'${esc(suite)}' 스위트를 삭제할까요?`;
    $('#sd-summary', root).innerHTML = `<span>TC <b class="num">${cur.count}</b>건</span><span>시트 <b class="num">${(cur.sheets || []).length}</b>개</span>`;
    const block = $('#sd-block', root);
    const ok = $('#sd-ok', root);
    block.hidden = true;
    ok.disabled = false;
    $('#suite-delete-modal', root).hidden = false;
    // 초안 생성이 진행 중이면 서버도 거절한다. 미리 막고 이유를 보여 준다
    const { job } = await api.authoringContext(suite).catch(() => ({ job: null }));
    if (state.suite === suite && job && ACTIVE_JOB.includes(job.status)) {
      block.textContent = '초안 생성이 진행 중입니다. 기획 정보 · TC 생성 화면에서 작업을 취소하거나 끝난 뒤 삭제하세요.';
      block.hidden = false;
      ok.disabled = true;
    }
  }

  async function deleteSuite() {
    const suite = state.suite;
    const ok = $('#sd-ok', root);
    ok.disabled = true;
    try {
      const { trash } = await api.deleteSuite(suite);
      $('#suite-delete-modal', root).hidden = true;
      try {
        sessionStorage.removeItem(`tcs-bundle:${suite}`);
        localStorage.removeItem(`tcs-job-dismissed:${suite}`);
      } catch (e) { /* 저장 불가 환경 */ }
      const names = state.suites.map((s) => s.suite);
      const i = names.indexOf(suite);
      const next = names[i + 1] || names[i - 1] || '';
      await NS.reloadSuites(next);
      NS.toast(`'<b>${esc(suite)}</b>' 삭제됨${state.suite ? ` · '<b>${esc(state.suite)}</b>' 스위트로 전환했습니다` : ''}`, 'ok', [{
        id: 'suite-delete-undo', label: '되돌리기',
        fn: async () => { await api.restoreTrash(trash.trash_id); await NS.reloadSuites(suite); NS.toast(`'${esc(suite)}' 스위트를 복원했습니다.`, 'ok'); },
      }], 12000);
    } catch (err) {
      const block = $('#sd-block', root);
      block.textContent = `삭제하지 못했습니다: ${err.message}`;
      block.hidden = false;
      ok.disabled = err.code === 'JOB_RUNNING';
    }
  }

  async function openTrash() {
    toggleSuiteMenu(false);
    $('#trash-modal', root).hidden = false;
    await renderTrash();
  }

  async function renderTrash() {
    const { items, retention_days: days } = await api.trash();
    $('#trash-n', root).textContent = items.length;
    $('#tr-help', root).textContent = `${days}일이 지나면 영구 삭제됩니다`;
    $('#trash-list', root).innerHTML = items.map((t) => {
      const left = Math.max(0, Math.ceil((new Date(t.expires_at) - Date.now()) / 86400000));
      return `<li data-trash="${esc(t.trash_id)}"><div><b>${esc(t.suite)}</b><div class="help">TC ${t.cases}건 · 시트 ${t.sheets}개 · ${esc(fmtTime(t.deleted_at))} 삭제 · ${left}일 남음</div>
        <div class="help err" data-id="trash-error" hidden></div></div>
        <button class="btn-sm" type="button" data-id="trash-restore" aria-label="'${esc(t.suite)}' 복원">복원</button>
        <button class="btn-sm btn-sm-danger" type="button" data-id="trash-purge" aria-label="'${esc(t.suite)}' 영구삭제">영구삭제</button></li>`;
    }).join('') || '<li class="faint" data-id="trash-empty">삭제한 스위트가 없습니다</li>';
    $$('[data-id="trash-restore"]', root).forEach((b) => b.addEventListener('click', async () => {
      const li = b.closest('li');
      b.disabled = true;
      try {
        const { restored } = await api.restoreTrash(li.dataset.trash);
        $('#trash-modal', root).hidden = true;
        await NS.reloadSuites(restored.suite);
        NS.toast(`'${esc(restored.suite)}' 스위트를 복원했습니다.`, 'ok');
      } catch (err) {
        const box = $('[data-id="trash-error"]', li);
        box.textContent = err.message;
        box.hidden = false;
        b.disabled = false;
      }
    }));
    $$('[data-id="trash-purge"]', root).forEach((b) => b.addEventListener('click', () => {
      const li = b.closest('li');
      const suite = items.find((t) => t.trash_id === li.dataset.trash).suite;
      const row = document.createElement('div');
      row.className = 'confirm-row';
      row.setAttribute('role', 'alert');
      row.innerHTML = `<span class="help err">'${esc(suite)}' 스위트를 영구삭제합니다. 복원할 수 없습니다.</span><span class="spacer"></span>
        <button class="btn-sm" type="button" data-id="trash-purge-cancel">취소</button>
        <button class="btn-sm btn-danger-solid" type="button" data-id="trash-purge-confirm">영구삭제 확정</button>`;
      li.appendChild(row);
      b.disabled = true;
      const cancel = $('[data-id="trash-purge-cancel"]', row);
      cancel.focus();
      cancel.addEventListener('click', () => { row.remove(); b.disabled = false; b.focus(); });
      $('[data-id="trash-purge-confirm"]', row).addEventListener('click', async (ev) => {
        ev.target.disabled = true;
        try {
          await api.purgeTrash(li.dataset.trash, suite);
          NS.toast(`'${esc(suite)}' 스위트를 영구삭제했습니다.`, 'ok');
          await renderTrash();
        } catch (err) {
          if (err.status === 404) { await renderTrash(); return; }
          const box = $('[data-id="trash-error"]', li);
          box.textContent = err.message;
          box.hidden = false;
          row.remove();
          b.disabled = false;
        }
      });
    }));
  }

  // 화면 이벤트에서 시작한 요청이 실패하면(서버 재시작·네트워크 끊김) 처리되지 않은 오류로 남기지 않고
  // 토스트로 알린다. 스튜디오가 화면에 있을 때만 가로챈다 (다른 대시보드 화면의 오류는 건드리지 않는다).
  window.addEventListener('unhandledrejection', (e) => {
    if (!root || !document.body.contains(root)) return;
    e.preventDefault();
    NS.toast(`요청을 처리하지 못했습니다: ${esc((e.reason && e.reason.message) || e.reason)}`, 'err');
  });

  let dialogObserver = null, dialogOpener = null, activeDialog = null;
  const dialogControls = (modal) => [...modal.querySelectorAll('button,input,select,textarea,a[href],[tabindex="0"]')]
    .filter(el => !el.disabled && el.getClientRects().length);
  function dialogKeys(e) {
    if (!activeDialog) return;
    if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation();
      const close = activeDialog.querySelector('[id$="-close"],[id$="-cancel"]');
      if (close) close.click();
    } else if (e.key === 'Tab') {
      const controls = dialogControls(activeDialog);
      const first = controls[0], last = controls.at(-1);
      if (!first) { e.preventDefault(); return; }
      if (e.shiftKey && (document.activeElement === first || !activeDialog.contains(document.activeElement))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !activeDialog.contains(document.activeElement))) {
        e.preventDefault(); first.focus();
      }
    }
  }
  function watchDialogs() {
    if (dialogObserver) dialogObserver.disconnect();
    activeDialog = dialogOpener = null;
    root.removeEventListener('keydown', dialogKeys);
    root.addEventListener('keydown', dialogKeys);
    dialogObserver = new MutationObserver(() => {
      const modal = root.querySelector('.scrim:not([hidden])');
      if (modal === activeDialog) return;
      if (modal) {
        dialogOpener = document.activeElement;
        activeDialog = modal;
        if (!modal.contains(document.activeElement)) dialogControls(modal)[0]?.focus();
      } else {
        activeDialog = null;
        if (dialogOpener && dialogOpener.isConnected) dialogOpener.focus();
        dialogOpener = null;
      }
    });
    dialogObserver.observe(root, {attributes:true, subtree:true, attributeFilter:['hidden']});
  }

  async function init(selector) {
    root = document.querySelector(selector);
    root.innerHTML = shellHtml();
    watchDialogs();
    available().forEach((s) => NS[s.module].mount(root));
    if (NS.importModal) NS.importModal.mount(root);
    $$('.step-item', root).forEach((b) => b.addEventListener('click', () => show(b.dataset.screen)));
    if (NS.importModal) $('#btn-import-xlsx', root).addEventListener('click', () => NS.importModal.open());
    $('#btn-start-blank', root).addEventListener('click', async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const result = await api.startBlank();
        await NS.reloadSuites(result.suite);
        NS.toast('빈 양식이 준비됐습니다. 기획 정보를 추가하고 시트·분류를 정하세요.', 'ok');
      } catch (err) {
        NS.toast(`빈 양식을 만들지 못했습니다: ${esc(err.message)}`, 'err');
      } finally {
        button.disabled = false;
      }
    });
    $('#suite-menu-btn', root).addEventListener('click', (e) => { e.stopPropagation(); toggleSuiteMenu($('#suite-menu', root).hidden); });
    document.addEventListener('click', (e) => { if (!e.target.closest('.suite-menu-wrap')) toggleSuiteMenu(false); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') toggleSuiteMenu(false); });
    $('#suite-menu-delete', root).addEventListener('click', openSuiteDelete);
    $('#suite-menu-trash', root).addEventListener('click', openTrash);
    $('#sd-cancel', root).addEventListener('click', () => { $('#suite-delete-modal', root).hidden = true; });
    $('#sd-ok', root).addEventListener('click', deleteSuite);
    $('#sd-backup', root).addEventListener('click', () => {
      $('#suite-delete-modal', root).hidden = true;
      show('export');
      NS.toast('범위를 <b>전체</b>로 두고 <b>검사 실행 → 내려받기</b>로 백업한 뒤 다시 삭제하세요.', '', [], 6000);
    });
    $('#tr-close', root).addEventListener('click', () => { $('#trash-modal', root).hidden = true; });
    $('#suite-select', root).addEventListener('change', async (e) => {
      const next = e.target.value;
      if (!(await NS.detail.confirmLeave())) { e.target.value = state.suite; return; }
      await NS.reloadSuites(next);
    });
    // 첫 화면은 스위트를 읽은 뒤 한 번만 고른다 (먼저 라이브러리를 띄우면 깜빡인다).
    // 다른 메뉴에서 돌아와도 처음 들어온 것처럼 고르도록 이전 스위트를 비운다
    state.suite = '';
    let firstSuite = '';
    try {
      const { suites } = await api.suites();
      if (!suites.some((suite) => suite.suite === DEFAULT_SUITE)) await api.startBlank();
      firstSuite = DEFAULT_SUITE;
    } catch (err) {
      NS.toast(`기본양식을 준비하지 못했습니다: ${esc(err.message)}`, 'err');
    }
    // 폴백은 불러오기 실패·스위트 없음일 때만. 불러오는 사이 사용자가 스위트를 바꿔 이 호출이 먼저 빠진 경우엔
    // 새 선택이 화면을 고른다 (여기서 라이브러리를 띄우면 새 선택이 '사용자가 탭을 눌렀다'고 보고 물러난다)
    try { await NS.reloadSuites(firstSuite); } catch (err) { if (!$('.screen.active', root)) show('library', true); throw err; }
    if (!state.suites.length && !$('.screen.active', root)) show('generate', true);
    if (NS.importModal && new URLSearchParams(window.location.search).get('import') === '1') NS.importModal.open();
  }

  async function refresh() {
    // Refresh server lists without remounting the authoring form or detail draft.
    await NS.library.refresh();
    await NS.refreshCounts();
    if (state.screen === 'review' && NS.reviewView) NS.reviewView.onShow();
  }

  window.TCS = { init, refresh };
})(window.TCS_NS = window.TCS_NS || {});
