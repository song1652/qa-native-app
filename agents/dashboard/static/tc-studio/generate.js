// TC 스튜디오 — 새로 생성: 소스 수집 · 대상 가지 · 작성 프로필 · 작업 진행 (목업 2번 화면, PRD F1·F3·F4)
// Phase 3는 registerSourceTab()으로 URL·Confluence·Figma 탭을 끼워 넣는다.
(function (NS) {
  'use strict';

  const { state, api, esc, $, $$, toast } = NS;
  const STEPS = [['queued', '대기'], ['fetching', '수집'], ['drafting', '초안 작성'], ['validating', '검증'], ['done', '완료']];
  const ICON = { file: 'PDF', paste: 'T', url: 'URL', conf: 'C', figma: 'F' };
  const tabs = [];            // {id, label, html(), mount(root, addSource)}
  let root = null;
  let bundle = { bundle_id: '', sources: [] };
  let profiles = [];
  let job = null;
  let poll = null;
  let startedHere = '';       // 이 화면에서 시작한 작업 id. 아니면 "지난 작업"으로 표시한다
  const DISMISS_KEY = () => `tcs-job-dismissed:${state.suite}`;

  NS.generateView = { html, mount, onShow, registerSourceTab, prefill, loadSuite, finishIfReviewed };

  function registerSourceTab(tab) { tabs.push(tab); }

  // ── Phase 2 기본 소스 탭: 파일 · 붙여넣기 ─────────────────────
  registerSourceTab({
    id: 'file', label: 'PRD 파일',
    html: () => `<label class="drop" id="src-file-drop" data-id="src-file-drop" for="src-file-input">
        <b>파일을 끌어다 놓거나 눌러서 선택</b><span class="faint">.pdf · .docx · .md · .txt · 최대 25MB · PDF 200쪽</span></label>
      <input type="file" id="src-file-input" data-id="src-file-input" accept=".pdf,.docx,.md,.txt" hidden>`,
    mount: (r, add) => {
      const drop = $('#src-file-drop', r);
      const pick = async (file) => {
        if (!file) return;
        if (!/\.(pdf|docx|md|txt)$/i.test(file.name)) { toast(`${esc(file.name)}: .pdf .docx .md .txt만 올릴 수 있습니다.`, 'err'); return; }
        if (file.size > 25 * 1024 * 1024) { toast(`${esc(file.name)}: 25MB를 넘습니다.`, 'err'); return; }
        await add((id) => api.addSourceFile(id, file));
      };
      ['dragover', 'dragenter'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
      ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove('over')));
      drop.addEventListener('drop', (e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); });
      $('#src-file-input', r).addEventListener('change', (e) => { pick(e.target.files[0]); e.target.value = ''; });
    },
  });
  registerSourceTab({
    id: 'paste', label: '텍스트 붙여넣기',
    html: () => `<div class="field"><textarea class="textarea" id="src-paste" data-id="src-paste" rows="6" placeholder="기획 문서 본문을 붙여넣으세요 (최대 1MB)"></textarea>
      <div class="row"><span class="help" id="paste-size">0 KB / 1 MB</span><span class="spacer"></span><button class="btn-sm" data-id="src-paste-add" id="src-paste-add">소스로 추가</button></div></div>`,
    mount: (r, add) => {
      $('#src-paste', r).addEventListener('input', (e) => {
        const n = new Blob([e.target.value]).size;
        $('#paste-size', r).textContent = `${(n / 1024).toFixed(1)} KB / 1 MB`;
        $('#paste-size', r).className = 'help' + (n > 1048576 ? ' err' : '');
      });
      $('#src-paste-add', r).addEventListener('click', async () => {
        const text = $('#src-paste', r).value.trim();
        if (!text) { toast('붙여넣은 내용이 없습니다.', 'err'); return; }
        if (await add((id) => api.addSourcePaste(id, text))) $('#src-paste', r).value = '';
      });
    },
  });

  function html() {
    return `
  <section class="screen" id="screen-generate" data-screen="generate">
    <div class="wrap"><div class="gen">
      <div class="panel">
        <div class="panel-head">1. 기획 정보 입력</div>
        <div class="panel-body" style="display:grid;gap:12px">
          <p class="help" style="margin:0">PRD 파일을 올리거나 텍스트·URL·Confluence·Figma 탭에서 기획 정보를 추가하세요. 입력한 내용을 바탕으로 LLM이 TC 초안을 작성합니다.</p>
          <div class="src-tabs" role="tablist">${tabs.map((t, i) => `<button class="src-tab" role="tab" data-id="src-tab-${t.id}" data-src="${t.id}" aria-selected="${i === 0}">${esc(t.label)}</button>`).join('')}</div>
          ${tabs.map((t, i) => `<div data-srcpane="${t.id}" ${i ? 'hidden' : ''}>${t.html()}</div>`).join('')}
          <div id="src-extra"></div>
          <div class="label" style="margin-top:4px">수집한 소스 <span id="src-n" class="num">0</span></div>
          <div class="srcs" id="srcs" data-id="src-list"></div>
        </div>
      </div>
      <div style="display:grid;gap:16px">
        <div class="panel"><div class="panel-head">2. 작성할 시트·분류</div>
          <div class="panel-body" style="display:grid;gap:10px">
            <div class="field"><span class="label">시트</span><div class="row" style="flex-wrap:nowrap"><select class="select" id="gen-target-sheet" data-id="gen-target-sheet" style="min-width:0"></select><button class="btn-sm" type="button" data-id="gen-add-sheet" id="gen-add-sheet" style="white-space:nowrap;flex-shrink:0">시트 추가</button><button class="btn-sm" type="button" data-id="gen-rename-sheet" id="gen-rename-sheet" style="white-space:nowrap;flex-shrink:0" disabled>이름 변경</button></div></div>
            <div class="field app-only"><label class="label" for="gen-platforms">대상 플랫폼</label><select class="select" id="gen-platforms"><option value="both">둘 다</option><option value="android">And</option><option value="ios">iOS</option></select></div>
            <div class="picker" data-id="gen-target-path">
              ${[['l1', '대분류'], ['l2', '중분류'], ['l3', '소분류']].map(([k, l]) => `<div class="field"><span class="label">${l}</span>
                <select class="select" id="gen-path-${k}" data-id="gen-path-${k}"></select>
                <input class="input" id="gen-new-${k}" data-id="gen-new-${k}" placeholder="새 ${l} 이름" hidden></div>`).join('')}
            </div>
            <div class="row"><button class="btn-sm" type="button" id="gen-add-branch" data-id="gen-add-branch" disabled>분류 추가</button><span class="help">대분류를 입력하세요. 중·소분류는 선택 사항입니다.</span></div>
            <div class="examples" data-id="gen-style-examples" id="gen-examples"></div>
          </div></div>
        <div class="panel"><div class="panel-head">작성 규칙<span class="spacer"></span><button class="btn-sm" data-id="gen-profile-edit" id="gen-profile-edit">규칙 편집</button></div>
          <div class="panel-body" style="display:grid;gap:10px">
            <select class="select" id="gen-profile" data-id="gen-profile"></select>
            <ul class="profile-rules" id="gen-rules"></ul>
            <div id="gen-profile-editor" hidden style="display:grid;gap:8px">
              <div class="row"><span class="help">규칙 (한 줄에 하나)</span><span class="spacer"></span>
                <label class="btn-sm" for="gen-style-file" data-id="gen-style-import" title="기존 TC 엑셀의 제목·Step·Expected 말투를 읽어 규칙·끝맺음·기준 예시를 채웁니다">엑셀에서 문체 가져오기</label>
                <input type="file" id="gen-style-file" data-id="gen-style-file" accept=".xlsx" hidden></div>
              <textarea class="textarea" id="gen-rules-input" data-id="gen-rules-input" rows="6" aria-label="규칙 (한 줄에 하나)"></textarea>
              <label class="help">금지 표현 (쉼표로 구분)<input class="input" id="gen-banned-input" data-id="gen-banned-input"></label>
              <label class="help">Expected 끝맺음 (쉼표로 구분 · 비우면 검사하지 않음)<input class="input" id="gen-endings-input" data-id="gen-endings-input" placeholder="예: 된다., 는다."></label>
              <div class="help" id="gen-profile-examples" data-id="gen-profile-examples"></div>
              <div class="row"><input class="input" id="gen-profile-name" data-id="gen-profile-name" placeholder="저장할 프로필 이름" style="max-width:220px">
                <button class="btn-sm" data-id="gen-profile-save" id="gen-profile-save">저장</button></div>
            </div>
          </div></div>
        <div class="panel"><div class="panel-body" style="display:grid;gap:12px" id="job-panel" data-id="job-panel">
          <div class="row"><button class="btn btn-primary" data-id="gen-submit" id="gen-submit" disabled>초안 생성</button><span class="help" id="gen-hint">소스를 하나 이상 추가하세요</span></div>
          <div class="job" id="job" hidden>
            <div class="row"><b id="job-title"></b><span id="job-pill"></span><span class="help" id="job-when" data-id="job-when"></span><span class="spacer"></span><button class="btn-sm" data-id="job-cancel" id="job-cancel">취소</button><button class="icon-btn" data-id="job-dismiss" id="job-dismiss" aria-label="지난 작업 닫기" title="지난 작업 닫기">✕</button></div>
            <div class="jsteps" id="jsteps" data-id="job-progress"></div>
            <div class="help" id="job-detail"></div>
            <div id="job-fail" hidden class="warnbox err">
              <b id="job-fail-title"></b><span id="job-fail-body"></span>
              <div class="log" data-id="job-log-tail" id="job-log"></div>
              <div class="row"><button class="btn btn-primary" data-id="job-retry" id="job-retry">실패한 섹션만 다시 생성</button>
                <button class="btn btn-ghost" data-id="job-open-review-partial" id="job-open-review-partial">살린 초안 검토</button></div>
            </div>
            <div id="job-done" hidden class="row"><span class="tag ok" id="job-done-tag"></span>
              <button class="btn btn-success" data-id="job-open-review" id="job-open-review">초안 검토로 이동</button></div>
          </div>
        </div></div>
      </div>
    </div></div>
  </section>
  <div class="scrim" id="sheet-rename-modal" data-id="sheet-rename-modal" hidden>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="sheet-rename-title" style="width:min(440px,100%)">
      <div class="panel-head" id="sheet-rename-title">시트 이름 변경</div>
      <div class="panel-body" style="display:grid;gap:16px">
        <div class="field"><label class="label" for="sheet-rename-name">시트 이름</label>
          <input class="input" id="sheet-rename-name" data-id="sheet-rename-name" maxlength="31" placeholder="예: 회원가입, 결제, 검색" autocomplete="off" aria-describedby="sheet-rename-help sheet-rename-error">
          <span class="help" id="sheet-rename-help">최대 31자. 기존 TC 내용과 ID는 유지됩니다.</span>
          <span class="help" id="sheet-rename-error" data-id="sheet-rename-error" role="alert" style="color:var(--err)"></span></div>
        <div class="row"><span class="spacer"></span><button class="btn btn-ghost" id="sheet-rename-cancel" data-id="sheet-rename-cancel">취소</button><button class="btn btn-primary" id="sheet-rename-save" data-id="sheet-rename-save">저장</button></div>
      </div>
    </div>
  </div>`;
  }

  // ── 소스 목록 ────────────────────────────────────────────────
  const BUNDLE_KEY = () => `tcs-bundle:${state.suite}`;

  async function ensureBundle() {
    if (bundle.bundle_id) return bundle.bundle_id;
    const { bundle_id: id } = await api.newBundle();
    bundle = { bundle_id: id, sources: [] };
    try { sessionStorage.setItem(BUNDLE_KEY(), id); } catch (e) { /* 저장 불가 환경 */ }
    return id;
  }

  // 소스 탭이 부르는 공용 추가 함수. 성공하면 true
  async function addSource(call) {
    try {
      const id = await ensureBundle();
      const { source } = await call(id);
      bundle.sources.push(source);
      renderSources();
      toast(`${esc(source.title)} 추가 · ${source.chars.toLocaleString()}자 · 섹션 ${source.sections}개`, 'ok', [], 2000);
      return true;
    } catch (err) {
      toast(`소스를 추가하지 못했습니다: ${esc(err.message)}`, 'err');
      return false;
    }
  }
  NS.generateView.addSource = addSource;
  NS.generateView.ensureBundle = ensureBundle;
  NS.generateView.pushSource = (source) => { bundle.sources.push(source); renderSources(); };   // Phase 3 (Confluence 여러 페이지)

  function renderSources() {
    $('#srcs', root).innerHTML = bundle.sources.map((s) => `<div class="src-card" data-id="src-chip">
      <div class="src-ico ${s.kind}">${ICON[s.kind] || '?'}</div>
      <div style="min-width:0"><div class="src-title">${esc(s.title)}</div><div class="src-meta"><span class="src-ref">${esc(s.ref)}</span>
        <span class="tag">${s.chars.toLocaleString()}자</span>${s.pages ? `<span class="tag">${s.pages}쪽</span>` : ''}<span class="tag">섹션 ${s.sections}</span>
        ${s.truncated ? '<span class="tag warn">잘림</span>' : ''}${s.warnings.map((w) => `<span class="tag warn">${esc(w)}</span>`).join('')}</div></div>
      <button class="icon-btn" data-id="src-chip-remove" data-sid="${s.source_id}" aria-label="소스 제거">✕</button></div>`).join('')
      || '<span class="help">아직 수집한 소스가 없습니다</span>';
    $$('[data-id="src-chip-remove"]', root).forEach((b) => b.addEventListener('click', async () => {
      await api.removeSource(bundle.bundle_id, b.dataset.sid);
      bundle.sources = bundle.sources.filter((s) => s.source_id !== b.dataset.sid);
      renderSources();
    }));
    $('#src-n', root).textContent = bundle.sources.length;
    updateSubmit();
  }

  // 소스와 대상(시트·대분류)이 모두 있어야 누를 수 있다. 빠진 것을 힌트로 알려 준다
  function updateSubmit() {
    const t = target();
    const hasTarget = Boolean(t.sheet && t.path[0]);
    const chars = bundle.sources.reduce((n, s) => n + s.chars, 0);
    $('#gen-submit', root).disabled = !bundle.sources.length || !hasTarget || isRunning();
    $('#gen-hint', root).textContent = !bundle.sources.length ? '소스를 하나 이상 추가하세요'
      : !hasTarget ? '넣을 시트와 대분류를 고르세요'
        : `소스 ${bundle.sources.length}개 · 약 ${chars.toLocaleString()}자 · 섹션마다 수 분 걸릴 수 있습니다`;
  }

  // ── 대상 가지 ────────────────────────────────────────────────
  function children(path) {
    let nodes = state.tree;
    for (const name of path) {
      const n = nodes.find((x) => x.name === name);
      nodes = n ? n.children.filter((c) => c.level !== 'feature') : [];
    }
    return nodes;
  }
  function fillSelect(id, names, cur, allowEmpty) {
    const sel = $(`#gen-path-${id}`, root) || $('#gen-target-sheet', root);
    sel.innerHTML = (allowEmpty ? '<option value="">(없음)</option>' : '')
      + names.map((n) => `<option ${n === cur ? 'selected' : ''}>${esc(n)}</option>`).join('')
      + (id !== 'sheet' ? `<option value="__new">+ 새로 만들기…</option>` : '');
  }
  function target() {
    const sheet = $('#gen-target-sheet', root).value;
    const path = ['l1', 'l2', 'l3'].map((k) => {
      const v = $(`#gen-path-${k}`, root).value;
      return v === '__new' ? $(`#gen-new-${k}`, root).value.trim() : v;
    });
    const selection = $('#gen-platforms', root).value;
    const platforms = selection === 'both' ? ['android', 'ios'] : [selection];
    return NS.isAppSuite() ? { sheet, path, platforms } : { sheet, path };
  }
  function renderTarget(keep = target()) {
    const sheets = [...new Set([...state.tree.map((n) => n.name),
      ...(state.suites.find((s) => s.suite === state.suite)?.sheets || [])])];
    const sheet = sheets.includes(keep.sheet) ? keep.sheet : '';
    $('#gen-target-sheet', root).innerHTML = '<option value="">시트를 선택하세요</option>' + sheets.map((n) => `<option ${n === sheet ? 'selected' : ''}>${esc(n)}</option>`).join('');
    $('#gen-rename-sheet', root).disabled = !sheet;
    $('#gen-add-branch', root).disabled = !sheet;
    const path = [];
    ['l1', 'l2', 'l3'].forEach((k, i) => {
      const names = sheet ? children([sheet, ...path]).map((n) => n.name) : [];
      const cur = names.includes(keep.path[i]) ? keep.path[i] : (i === 0 ? names[0] || '' : '');
      fillSelect(k, names, cur, i > 0);
      $(`#gen-new-${k}`, root).hidden = $(`#gen-path-${k}`, root).value !== '__new';
      path.push(cur);
    });
    loadExamples();
    updateSubmit();
  }
  async function loadExamples() {
    const t = target();
    if (!state.suite || !t.sheet) { $('#gen-examples', root).innerHTML = ''; return; }
    const { items, total } = await api.list(state.suite, { path: [t.sheet, ...t.path.filter(Boolean)].join('/'), status: 'approved', limit: 10 });
    const fill = (profile().style_examples || []).length;
    if (!total) { $('#gen-examples', root).innerHTML = `<span class="faint">${fill ? `같은 가지에 기존 TC가 없어 프로필 기준 예시 ${fill}건의 말투로 생성합니다.` : '기존 TC가 없어 입력한 정보와 작성 규칙으로 생성합니다.'}</span>`; return; }
    $('#gen-examples', root).innerHTML = `<span class="faint">같은 가지의 문체 예시 ${Math.min(total, profile().examples || 8)}건을 함께 넣습니다 (권장 5~10건)</span>`
      + (items.length ? `<span>${items.slice(0, 4).map((c) => `· ${esc(c.case_id)} ${esc(c.feature)}`).join(' ')}</span>` : '<span class="faint">이 가지에는 예시가 없습니다</span>');
  }

  // ── 작성 프로필 ──────────────────────────────────────────────
  const profile = () => profiles.find((p) => p.name === $('#gen-profile', root).value) || profiles[0] || { rules: [], examples: 8, style_examples: [], expected_endings: [] };
  let editExamples = [];   // 편집 중인 기준 예시 (엑셀에서 가져오면 바뀐다)
  const splitList = (v) => v.split(',').map((x) => x.trim()).filter(Boolean);
  function renderEditExamples() {
    $('#gen-profile-examples', root).innerHTML = editExamples.length
      ? `기준 예시 ${editExamples.length}건 — 같은 가지에 승인된 TC가 모자랄 때 이 말투를 따라 씁니다<br>${editExamples.map((e) => `· ${esc(e.feature)} → ${esc(e.expected)}`).join('<br>')}`
      : '기준 예시 없음 — 엑셀에서 문체를 가져오면 채워집니다';
  }
  async function loadProfiles(select) {
    profiles = (await api.profiles()).profiles;
    $('#gen-profile', root).innerHTML = profiles.map((p) => `<option ${p.name === select ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
    renderRules();
  }
  function renderRules() {
    const p = profile();
    $('#gen-rules', root).innerHTML = p.rules.map((r) => `<li>${esc(r)}</li>`).join('')
      + (p.banned_phrases && p.banned_phrases.length ? `<li>금지: ${p.banned_phrases.map((b) => `"${esc(b)}"`).join(', ')}</li>` : '')
      + ((p.expected_endings || []).length ? `<li>Expected 끝맺음: ${p.expected_endings.map((e) => `"${esc(e)}"`).join(', ')}</li>` : '')
      + ((p.style_examples || []).length ? `<li>기준 예시 ${p.style_examples.length}건</li>` : '');
  }

  // ── 작업 ─────────────────────────────────────────────────────
  const isRunning = () => job && ['queued', 'fetching', 'drafting', 'validating'].includes(job.status);

  async function submit(extra = {}) {
    const t = target();
    if (!t.sheet || !t.path[0]) { toast('넣을 시트와 대분류를 고르세요.', 'err'); return; }
    try {
      const res = await api.startJob(state.suite, { bundle_id: bundle.bundle_id, sheet: t.sheet, path: t.path,
        ...(NS.isAppSuite() ? { platforms: t.platforms } : {}), profile: profile().name, ...extra });
      job = res.job;
      startedHere = job.job_id;
      renderJob({ job, log: '', invalid: [] });
      startPolling();
    } catch (err) {
      toast(err.code === 'JOB_RUNNING' ? '이미 실행 중인 생성 작업이 있습니다. 끝난 뒤 다시 시도하세요.' : `생성을 시작하지 못했습니다: ${esc(err.message)}`, 'err');
    }
  }
  function startPolling() {
    clearInterval(poll);
    const suite = state.suite, jobId = job.job_id;
    poll = setInterval(async () => {
      const body = await api.job(jobId);
      if (state.suite !== suite || !job || job.job_id !== jobId) return;
      job = body.job;
      renderJob(body);
      if (!isRunning()) {
        clearInterval(poll);
        await NS.library.refresh();
        await NS.refreshCounts();
        if (job.status === 'done') toast(`초안 ${job.kept}건이 준비됐습니다.`, 'ok', [{ id: 'toast-open-review', label: '검토하기', fn: () => openReview() }]);
      }
    }, 1500);
  }
  function renderJob(body) {
    const j = body.job;
    $('#job', root).hidden = false;
    $('#job-title', root).textContent = `작업 ${j.job_id}`;
    // 화면을 다시 열면 스위트의 마지막 작업을 복원한다. 방금 실행한 작업과 헷갈리지 않게 시각을 붙인다
    const past = j.job_id !== startedHere && !isRunning();
    $('#job-when', root).textContent = past ? `지난 작업 · ${(j.created_at || '').replace('T', ' ').slice(5, 16)}` : '';
    $('#job-dismiss', root).hidden = isRunning();
    const failed = ['failed', 'cancelled'].includes(j.status);
    $('#job-pill', root).innerHTML = `<span class="pill ${failed ? 'st-rejected' : j.status === 'done' ? 'st-approved' : 'st-draft'}">${esc(j.status)}</span>`;
    const at = Math.max(STEPS.findIndex(([k]) => k === j.status), 0);
    $('#jsteps', root).innerHTML = STEPS.map(([k, l], i) => {
      const cls = j.status === 'done' || i < at ? 'done' : i === at ? (failed ? 'fail' : 'run') : '';
      return `<div class="jstep ${failed && i === 2 ? 'fail' : cls}"><div class="bar"><i></i></div><span>${l}</span></div>`;
    }).join('');
    const doneSections = j.sections.filter((s) => s.status === 'done').length;
    $('#job-detail', root).textContent = j.sections.length ? `섹션 ${doneSections}/${j.sections.length} · 초안 ${j.kept}건 · 형식 오류 ${j.invalid}건 · $${j.cost_usd}` : '';
    $('#job-cancel', root).hidden = !isRunning();
    updateSubmit();
    $('#job-done', root).hidden = j.status !== 'done';
    $('#job-done-tag', root).textContent = `초안 ${j.kept}건 · 형식 오류 ${j.invalid}건`;
    $('#job-fail', root).hidden = !failed;
    if (failed) {
      const failedSections = j.sections.filter((s) => s.status === 'failed');
      $('#job-fail-title', root).textContent = j.status === 'cancelled' ? '작업을 취소했습니다' : '일부 섹션을 만들지 못했습니다';
      $('#job-fail-body', root).textContent = `${j.reason || ''} · 살린 초안 ${j.kept}건`;
      $('#job-log', root).textContent = body.log;
      $('#job-retry', root).hidden = !failedSections.length;
      $('#job-retry', root).onclick = () => submit({ only_refs: failedSections.flatMap((s) => s.refs) });
      $('#job-open-review-partial', root).hidden = !j.kept;
    }
  }
  function openReview() {
    if (job) state.reviewJob = job.job_id;
    NS.show('review');
  }

  // 커버리지 갭 등에서 대상 가지를 채워 들어올 때
  function prefill(t) {
    renderTarget({ sheet: t.sheet, path: [...t.path, '', '', ''].slice(0, 3) });
  }

  function onShow() {
    renderTarget();
    let saved = '';
    try { saved = sessionStorage.getItem(BUNDLE_KEY()) || ''; } catch (e) { saved = ''; }
    if (saved && saved !== bundle.bundle_id) {
      api.bundle(saved).then((b) => { bundle = { bundle_id: b.bundle_id, sources: b.sources }; renderSources(); }).catch(() => {});
    }
    renderSources();
  }

  async function loadSuite(savedJob, preserveTarget = false) {
    clearInterval(poll);
    const suite = state.suite;
    let saved = '';
    try { saved = sessionStorage.getItem(BUNDLE_KEY()) || ''; } catch (e) { /* 저장 불가 환경 */ }
    let dismissed = '';
    try { dismissed = localStorage.getItem(DISMISS_KEY()) || ''; } catch (e) { /* 저장 불가 환경 */ }
    const active = savedJob && ['queued', 'fetching', 'drafting', 'validating'].includes(savedJob.status);
    job = savedJob && savedJob.job_id === dismissed && !active ? null : savedJob;
    // 끝난 작업은 검토할 초안이 남아 있을 때만 복원한다. 검토를 마쳤으면 소스·대상까지 비운 처음 양식으로 시작한다
    let reviewed = false;
    if (job && !active) {
      const { total } = await api.list(suite, { job: job.job_id, status: 'draft', limit: 1 }).catch(() => ({ total: 0 }));
      if (state.suite !== suite) return;
      if (!total) { reviewed = true; job = null; }
    }
    if (reviewed && saved === savedJob.bundle_id) {
      saved = '';
      try { sessionStorage.removeItem(BUNDLE_KEY()); } catch (e) { /* 저장 불가 환경 */ }
    }
    const id = saved || (job && job.bundle_id);
    const loaded = id ? await api.bundle(id).catch(() => null) : null;
    if (state.suite !== suite) return;
    bundle = loaded ? { bundle_id: loaded.bundle_id, sources: loaded.sources } : { bundle_id: '', sources: [] };
    state.reviewJob = job ? job.job_id : null;
    const selected = target();
    renderTarget(preserveTarget && selected.sheet ? selected : job ? job.target : { sheet: '', path: ['', '', ''] });
    renderSources();
    await loadProfiles(job && job.profile);
    if (state.suite !== suite) return;
    if (job) {
      const body = await api.job(job.job_id);
      if (state.suite !== suite) return;
      renderJob(body);
      if (isRunning()) startPolling();
    } else {
      $('#job', root).hidden = true;
    }
  }

  // 생성 화면을 처음 양식으로 되돌린다. 옛 소스 묶음은 서버에 남아 이미 만든 초안의 원문 보기에 계속 쓰인다
  function resetForm() {
    clearInterval(poll);
    job = null;
    startedHere = '';
    state.reviewJob = null;
    bundle = { bundle_id: '', sources: [] };
    try { sessionStorage.removeItem(BUNDLE_KEY()); } catch (e) { /* 저장 불가 환경 */ }
    $('#job', root).hidden = true;
    renderTarget({ sheet: '', path: ['', '', ''] });
    renderSources();
  }

  // 검토 화면이 작업의 초안을 모두 처리했을 때 부른다
  function finishIfReviewed(jobId) {
    if (!job || job.job_id !== jobId || isRunning()) return false;
    resetForm();
    return true;
  }

  function mount(r) {
    root = r;
    $$('.src-tab', root).forEach((t) => t.addEventListener('click', () => {
      $$('.src-tab', root).forEach((x) => x.setAttribute('aria-selected', x === t));
      $$('[data-srcpane]', root).forEach((p) => { p.hidden = p.dataset.srcpane !== t.dataset.src; });
    }));
    tabs.forEach((t) => t.mount($(`[data-srcpane="${t.id}"]`, root), addSource));
    const sheetModal = $('#sheet-rename-modal', root);
    const sheetName = $('#sheet-rename-name', root);
    const sheetSave = $('#sheet-rename-save', root);
    const sheetCancel = $('#sheet-rename-cancel', root);
    const sheetError = $('#sheet-rename-error', root);
    let sheetMode = 'rename', sheetTarget = null, sheetOpener = null;
    function openSheetModal(mode, opener) {
      sheetMode = mode;
      sheetTarget = target();
      sheetOpener = opener;
      $('#sheet-rename-title', root).textContent = mode === 'add' ? '시트 추가' : '시트 이름 변경';
      $('#sheet-rename-help', root).textContent = mode === 'add' ? '최대 31자. 기존 양식의 서식만 복사하며 TC 내용은 비워 둡니다.' : '최대 31자. 기존 TC 내용과 ID는 유지됩니다.';
      sheetSave.textContent = mode === 'add' ? '추가' : '저장';
      sheetName.value = mode === 'add' ? '' : sheetTarget.sheet;
      sheetError.textContent = '';
      sheetModal.hidden = false;
      sheetName.focus();
      sheetName.select();
    }
    function closeSheetModal() {
      if (sheetSave.disabled) return;
      sheetModal.hidden = true;
      sheetOpener?.focus();
    }
    $('#gen-rename-sheet', root).addEventListener('click', (e) => openSheetModal('rename', e.currentTarget));
    $('#gen-add-sheet', root).addEventListener('click', (e) => openSheetModal('add', e.currentTarget));
    sheetCancel.addEventListener('click', closeSheetModal);
    sheetModal.addEventListener('click', (e) => { if (e.target === sheetModal) closeSheetModal(); });
    sheetModal.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); closeSheetModal(); }
      if (e.key === 'Enter' && e.target === sheetName) { e.preventDefault(); sheetSave.click(); }
      if (e.key === 'Tab') {
        if (e.shiftKey && e.target === sheetName) { e.preventDefault(); sheetSave.focus(); }
        else if (!e.shiftKey && e.target === sheetSave) { e.preventDefault(); sheetName.focus(); }
      }
    });
    sheetSave.addEventListener('click', async () => {
      const name = sheetName.value.trim();
      if (!name) { sheetError.textContent = '시트 이름을 입력하세요.'; sheetName.focus(); return; }
      sheetSave.disabled = true;
      sheetCancel.disabled = true;
      sheetError.textContent = '';
      try {
        if (sheetMode === 'add') await api.addSheet(state.suite, name);
        else await api.renameSheet(state.suite, sheetTarget.sheet, name);
        await NS.reloadSuites(state.suite);
        renderTarget({ sheet: name, path: sheetMode === 'add' ? ['', '', ''] : sheetTarget.path });
        sheetSave.disabled = false;
        closeSheetModal();
        toast(sheetMode === 'add' ? '빈 시트를 추가했습니다.' : '시트 이름을 변경했습니다.', 'ok');
      } catch (err) { sheetError.textContent = err.message; }
      finally { sheetSave.disabled = false; sheetCancel.disabled = false; }
    });
    $('#gen-add-branch', root).addEventListener('click', async () => {
      const t = target();
      try {
        await api.addBranch(state.suite, t.sheet, t.path);
        await NS.library.refresh();
        renderTarget(t);
        toast('분류를 추가했습니다.', 'ok');
      } catch (err) { toast(`분류를 추가하지 못했습니다: ${esc(err.message)}`, 'err'); }
    });
    $('#gen-target-sheet', root).addEventListener('change', () => renderTarget({ sheet: $('#gen-target-sheet', root).value, path: ['', '', ''] }));
    ['l1', 'l2', 'l3'].forEach((k, i) => $(`#gen-path-${k}`, root).addEventListener('change', (e) => {
      if (e.target.value === '__new') { $(`#gen-new-${k}`, root).hidden = false; $(`#gen-new-${k}`, root).focus(); return; }
      const t = target();
      renderTarget({ sheet: t.sheet, path: t.path.map((p, j) => (j <= i ? p : '')) });
    }));
    $('#gen-profile', root).addEventListener('change', () => { renderRules(); loadExamples(); });
    $('#gen-profile-edit', root).addEventListener('click', () => {
      const ed = $('#gen-profile-editor', root);
      ed.hidden = !ed.hidden;
      $('#gen-rules-input', root).value = profile().rules.join('\n');
      $('#gen-banned-input', root).value = (profile().banned_phrases || []).join(', ');
      $('#gen-endings-input', root).value = (profile().expected_endings || []).join(', ');
      editExamples = profile().style_examples || [];
      renderEditExamples();
      $('#gen-profile-name', root).value = profile().name === '기본' ? '' : profile().name;
    });
    $('#gen-style-file', root).addEventListener('change', async (e) => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      const label = $('[data-id="gen-style-import"]', root);
      label.classList.add('loading');
      try {
        const res = await api.styleFromXlsx(file);
        // 내용 규칙(추측 금지 등)은 두고, 같은 문체 규칙이 없을 때만 덧붙인다
        const current = $('#gen-rules-input', root).value.split('\n').map((r) => r.trim()).filter(Boolean);
        $('#gen-rules-input', root).value = [...current, ...res.rules.filter((r) => !current.includes(r))].join('\n');
        $('#gen-endings-input', root).value = res.expected_endings.join(', ');
        editExamples = res.style_examples;
        renderEditExamples();
        if (!$('#gen-profile-name', root).value.trim()) $('#gen-profile-name', root).value = file.name.normalize('NFC').replace(/\.xlsx$/i, '').replace(/_?Full$/i, '').slice(0, 40);
        toast(`TC ${res.stats.cases}건에서 문체를 읽었습니다. 규칙을 확인하고 저장하세요.`, 'ok');
      } catch (err) { toast(`문체를 읽지 못했습니다: ${esc(err.message)}`, 'err'); }
      finally { label.classList.remove('loading'); }
    });
    $('#gen-profile-save', root).addEventListener('click', async () => {
      const name = $('#gen-profile-name', root).value.trim();
      const rules = $('#gen-rules-input', root).value.split('\n').map((r) => r.trim()).filter(Boolean);
      try {
        await api.saveProfile(name, { ...profile(), rules, banned_phrases: splitList($('#gen-banned-input', root).value),
          expected_endings: splitList($('#gen-endings-input', root).value), style_examples: editExamples });
        await loadProfiles(name);
        $('#gen-profile-editor', root).hidden = true;
        toast(`작성 프로필 "${esc(name)}"을 저장했습니다.`, 'ok');
      } catch (err) { toast(`저장하지 못했습니다: ${esc(err.message)}`, 'err'); }
    });
    $('#gen-submit', root).addEventListener('click', () => submit());
    $('#job-cancel', root).addEventListener('click', () => api.cancelJob(job.job_id));
    $('#job-dismiss', root).addEventListener('click', () => {
      try { localStorage.setItem(DISMISS_KEY(), job.job_id); } catch (e) { /* 저장 불가 환경 */ }
      job = null;
      state.reviewJob = null;
      $('#job', root).hidden = true;
      updateSubmit();
    });
    ['l1', 'l2', 'l3'].forEach((k) => $(`#gen-new-${k}`, root).addEventListener('input', updateSubmit));
    ['#job-open-review', '#job-open-review-partial'].forEach((s) => $(s, root).addEventListener('click', openReview));
    loadProfiles();
  }
})(window.TCS_NS = window.TCS_NS || {});
