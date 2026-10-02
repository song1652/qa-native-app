// TC 스튜디오 — 초안 검토: 승인·반려·재생성·중복 처리·원문 발췌·커버리지 갭 (목업 3번 화면, PRD F5.5~F5.7, F5.10)
(function (NS) {
  'use strict';

  const { state, api, esc, $, $$, toast } = NS;
  let root = null;
  let drafts = [];          // 이번 검토 대상 (작업 id가 있으면 그 작업의 초안 전부, 없으면 draft 상태 전부)
  let targets = {};         // 중복 후보 case_id → 케이스
  let jobInfo = null;
  let manifest = null;      // 작업 소스 묶음 (Figma 프레임 이미지용, Phase 3)
  let suiteDrafts = 0;      // 스위트 전체 draft 수 (상단 탭 배지와 같은 기준)
  let focus = 0;
  let filter = 'all';
  let sourceSeq = 0;

  NS.reviewView = { html, mount, onShow };

  function html() {
    return `
  <section class="screen" id="screen-review" data-screen="review">
    <div class="review">
      <div class="rv-left">
        <div class="rv-summary">
          <span><b id="rv-left">0</b> <span class="muted">건 남음</span></span>
          <span class="tag ok">승인 <span id="rv-ok" class="num">0</span></span>
          <span class="tag err">반려 <span id="rv-rej" class="num">0</span></span>
          <span class="tag warn">중복 후보 <span id="rv-dup" class="num">0</span></span>
          <span class="tag err">검증 오류 <span id="rv-err" class="num">0</span></span>
          <span class="spacer"></span>
          <span class="faint" style="font-size:11px"><span class="kbd">J</span><span class="kbd">K</span> 이동 <span class="kbd">A</span> 승인 <span class="kbd">R</span> 반려 <span class="kbd">G</span> 재생성 <span class="kbd">E</span> 편집</span>
          <button class="btn btn-ghost" data-id="review-approve-clean" id="review-approve-clean" title="중복·검증 오류·추정 문구·문체 경고가 없는 초안만">문제없는 초안 일괄 승인</button>
        </div>
        <div class="rv-list-pane"><div class="row">
          <div class="seg" role="group" aria-label="검토 필터" data-id="review-filter">
            <button aria-pressed="true" data-f="all">전체</button><button aria-pressed="false" data-f="pending">미검토</button><button aria-pressed="false" data-f="dup">중복 후보</button><button aria-pressed="false" data-f="invalid">검증 오류</button>
          </div>
          <span class="help" id="rv-job"></span><span class="spacer"></span>

        </div>
        <div id="rv-invalid" data-id="review-invalid"></div>
        <div id="review-case-list" aria-label="초안 목록"></div>
        </div>
        <div id="drafts" data-id="draft-list" style="display:grid;gap:10px"></div>
      </div>
      <aside class="rv-right" aria-label="원문">
        <div class="row"><b>원문</b><span class="spacer"></span><span class="src-ref" id="rv-ref"></span></div>
        <div class="excerpt" id="rv-excerpt" data-id="source-excerpt"><span class="faint">초안을 고르면 근거가 된 원문을 보여 줍니다</span></div>
        <div class="panel"><div class="panel-head">커버리지 갭 <span class="faint" style="font-weight:400" id="rv-cov-profile"></span><span class="spacer"></span><span class="faint" style="font-weight:400;font-size:10.5px">막대: 정상 · 예외 (빨강 = 없음)</span></div>
          <div class="panel-body"><ul class="gap-list" data-id="coverage-gap" id="rv-gaps"></ul></div></div>
      </aside>
    </div>
  </section>`;
  }

  const pending = (d) => d.status === 'draft';
  const unresolvedDup = (d) => (d.draft_meta.duplicates || []).length > 0 && !d.draft_meta.duplicate_checked;
  const estimated = (d) => d.bullets.some((b) => !b.verified);
  const styleIssues = (d) => d.issues.filter((x) => x.code.startsWith('STYLE_'));

  async function load() {
    if (!state.suite) return;
    const query = state.reviewJob ? { job: state.reviewJob, limit: 1000 } : { status: 'draft', limit: 1000 };
    drafts = (await api.list(state.suite, query)).items;
    jobInfo = state.reviewJob ? await api.job(state.reviewJob).catch(() => null) : null;
    manifest = jobInfo ? await api.bundle(jobInfo.job.bundle_id).catch(() => null) : null;
    suiteDrafts = jobInfo ? (await api.list(state.suite, { status: 'draft', limit: 1 })).total : 0;
    const ids = [...new Set(drafts.flatMap((d) => (d.draft_meta.duplicates || []).map((h) => h.case_id)))];
    targets = {};
    await Promise.all(ids.map(async (id) => { targets[id] = (await api.getCase(state.suite, id)).case; }));
    focus = Math.min(focus, Math.max(drafts.length - 1, 0));
    render();
    // 이 작업의 초안을 모두 승인·반려했으면 생성 화면을 처음 양식으로 되돌린다
    if (jobInfo && drafts.length && !drafts.some(pending) && NS.generateView
      && NS.generateView.finishIfReviewed(jobInfo.job.job_id)) {
      toast('이 작업의 초안 검토를 마쳤습니다. 생성 화면을 새 양식으로 비웠습니다.', 'ok');
    }
    await showSource();
    await loadGaps();
  }

  function card(d, i) {
    const dup = unresolvedDup(d) ? d.draft_meta.duplicates[0] : null;
    const target = dup ? targets[dup.case_id] : null;
    const errors = d.issues.filter((x) => x.level === 'error');
    const blocked = errors.length ? '검증 오류를 먼저 고치세요' : dup ? '중복 처리 방법을 먼저 고르세요' : '';
    return `<article class="dcard ${i === focus ? 'focus' : ''} ${d.status} ${dup ? 'dup' : ''} ${errors.length ? 'invalid' : ''}" data-id="draft-card" data-case="${d.case_id}" data-i="${i}" tabindex="0">
      <div class="draft-head"><span class="mono faint" style="font-size:11px">${d.case_id}</span><span class="draft-title">${esc(d.feature)}</span>
        <span class="pill st-${d.status}">${NS.STATUS_LABEL[d.status]}</span>${errors.length ? '<span class="tag err">검증 오류</span>' : ''}${estimated(d) ? '<span class="tag warn">추정 문구</span>' : ''}${styleIssues(d).length ? `<span class="tag warn" data-id="draft-style" title="${esc(styleIssues(d).map((x) => x.message).join('\n'))}">문체 확인</span>` : ''}${d.draft_meta.quote_found === false ? '<span class="tag warn" title="모델이 인용한 문장을 원문에서 찾지 못했습니다">인용 불일치</span>' : ''}
        <span class="spacer"></span><button class="src-ref" data-id="draft-source-ref">${esc(d.source_refs[0] || '')}</button></div>
      <dl class="draft-grid"><dt>경로</dt><dd>${esc(d.path.filter(Boolean).join(' › '))}</dd><dt>사전 조건</dt><dd>${esc(d.precondition) || '<span class="faint">없음</span>'}</dd>
        <dt>테스트 단계</dt><dd>${esc(d.steps.map((s, n) => `${n + 1}. ${s}`).join('\n'))}</dd>
        <dt>기대 결과</dt><dd>${esc(d.expected)}${d.bullets.map((b) => `\n- ${esc(b.text)}${b.verified ? '' : ' <span class="tag warn">추정</span>'}`).join('')}</dd>
        <dt>우선순위</dt><dd>${esc(d.priority) || '—'}</dd></dl>
      ${errors.length ? `<ul class="checks">${errors.map((x) => `<li><span class="bad">✕</span>${esc(x.message)}</li>`).join('')}</ul>` : ''}
      ${dup && target ? `<div class="dupbox" data-id="dup-resolution"><b>기존 케이스와 비슷합니다 · ${dup.case_id} (${Math.round(dup.similarity * 100)}%)</b>
        <div class="cmp"><div><span class="label">기존</span><div style="white-space:pre-wrap">${esc(target.expected)}</div></div><div><span class="label">초안</span><div style="white-space:pre-wrap">${esc(d.expected)}</div></div></div>
        <div class="seg" role="group" aria-label="중복 처리"><button data-id="dup-update" data-v="update">기존 케이스 갱신</button><button data-id="dup-skip" data-v="skip">건너뛰기</button><button data-id="dup-add" data-v="add">새로 추가</button></div></div>` : ''}
      <div class="row">
        <button class="btn btn-success" data-id="draft-approve" ${blocked || !pending(d) ? 'disabled' : ''} title="${blocked || '승인 (A)'}" style="padding:5px 12px">승인</button>
        <button class="btn btn-danger" data-id="draft-reject" ${!pending(d) ? 'disabled' : ''} style="padding:5px 12px">반려</button>
        <button class="btn btn-ghost" data-id="draft-edit" style="padding:5px 12px">편집</button>
        <button class="btn btn-ghost" data-id="draft-regen" ${jobInfo ? '' : 'disabled title="작업에서 온 초안만 재생성할 수 있습니다"'} style="padding:5px 12px">재생성…</button>
      </div>
      <div class="regen" data-regen hidden><textarea class="textarea" data-id="draft-regen-note" rows="2" placeholder="무엇을 바꿔야 하나요? 예) 배너 3개일 때와 5개일 때를 행으로 나눠 주세요"></textarea>
        <div class="row"><button class="btn-sm" data-id="draft-regen-submit">이 메모로 재생성</button><button class="btn-sm" data-id="draft-regen-cancel">닫기</button></div></div>
    </article>`;
  }

  function render() {
    const shown = drafts.map((d, i) => [d, i]).filter(([d]) => filter === 'all'
      || (filter === 'pending' && pending(d)) || (filter === 'dup' && unresolvedDup(d)) || (filter === 'invalid' && d.has_error));
    if (!shown.length) focus = -1;
    else if (!shown.some(([, i]) => i === focus)) focus = shown[0][1];
    $('#review-case-list', root).innerHTML = shown.map(([d, i]) => `<button class="review-case-item ${i === focus ? 'selected' : ''}" data-review-index="${i}" aria-pressed="${i === focus}"><span class="mono">${esc(d.case_id)}</span><b>${esc(d.feature)}</b><span class="pill st-${d.status}">${d.has_error ? '검증 오류' : unresolvedDup(d) ? '중복 후보' : NS.STATUS_LABEL[d.status]}</span><small>${esc(d.path.filter(Boolean).join(' › '))}</small></button>`).join('');
    $$('[data-review-index]', root).forEach(button => button.addEventListener('click', () => setFocus(+button.dataset.reviewIndex)));
    $('#drafts', root).innerHTML = shown.map(([d, i]) => card(d, i)).join('')
      || '<div class="empty-note faint" style="padding:30px;text-align:center">검토할 초안이 없습니다</div>';
    $('#rv-left', root).textContent = drafts.filter(pending).length;
    $('#rv-ok', root).textContent = drafts.filter((d) => d.status === 'approved').length;
    $('#rv-rej', root).textContent = drafts.filter((d) => d.status === 'rejected').length;
    $('#rv-dup', root).textContent = drafts.filter(unresolvedDup).length;
    $('#rv-err', root).textContent = drafts.filter((d) => d.has_error).length;
    // 상단 배지는 스위트 전체 초안 수, 이 화면은 작업 초안만 센다. 두 기준을 함께 보여 숫자가 달라 보이지 않게 한다
    const others = suiteDrafts - drafts.filter(pending).length;
    $('#rv-job', root).innerHTML = jobInfo
      ? `작업 ${esc(jobInfo.job.job_id)} · ${esc(jobInfo.job.status)} · 이 작업 초안만 표시${others > 0 ? ` <button class="btn-sm" data-id="review-show-all" id="review-show-all">다른 초안 ${others}건 포함해 보기</button>` : ''}`
      : '스위트의 모든 초안';
    const showAll = $('#review-show-all', root);
    if (showAll) showAll.addEventListener('click', () => { state.reviewJob = null; load(); });
    const invalid = jobInfo ? jobInfo.invalid : [];
    $('#rv-invalid', root).innerHTML = invalid.length ? `<details class="warnbox err"><summary>형식이 맞지 않아 버린 초안 ${invalid.length}건</summary>
      <ul class="checks">${invalid.map((x) => `<li><span class="bad">✕</span>${esc(x.raw.feature || '(이름 없음)')} — ${esc(x.errors.join(', '))}</li>`).join('')}</ul></details>` : '';
    bind();
  }

  async function decide(d, status) {
    if (status === 'approved' && (d.has_error || unresolvedDup(d))) {
      toast(d.has_error ? '검증 오류가 있는 초안은 승인할 수 없습니다. 편집하거나 재생성하세요.' : '중복 후보입니다. 처리 방법을 먼저 고르세요.', 'err');
      return;
    }
    try {
      await api.patchCase(state.suite, d.case_id, d.rev, { status });
      toast(`${d.case_id} ${status === 'approved' ? '승인' : '반려'}`, status === 'approved' ? 'ok' : '', [
        { id: 'draft-undo', label: '되돌리기', fn: async () => { const cur = (await api.getCase(state.suite, d.case_id)).case; await api.patchCase(state.suite, d.case_id, cur.rev, { status: 'draft' }); await load(); } }], 2500);
      focus = Math.min(focus + 1, drafts.length - 1);
      await load();
      await NS.refreshCounts();
    } catch (err) {
      toast(err.status === 409 ? '다른 곳에서 먼저 바뀌었습니다. 목록을 새로 불러왔습니다.' : esc(err.message), 'err');
      await load();
    }
  }

  async function regenerate(d, note, btn) {
    if (!note) { toast('재생성 메모를 적어 주세요. 무엇이 틀렸는지 알려야 결과가 달라집니다.', 'err'); return; }
    btn.textContent = '재생성 중…';
    btn.disabled = true;
    const j = jobInfo.job;
    try {
      const { job } = await api.startJob(state.suite, { bundle_id: j.bundle_id, sheet: j.target.sheet, path: j.target.path,
        profile: j.profile, mode: 'regenerate', case_id: d.case_id, note });
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const s = (await api.job(job.job_id)).job;
        if (!['queued', 'fetching', 'drafting', 'validating'].includes(s.status)) {
          toast(s.status === 'done' ? `${d.case_id}를 다시 만들었습니다. 이전 내용은 이력에 남습니다.` : `재생성 실패: ${esc(s.reason)}`, s.status === 'done' ? 'ok' : 'err');
          break;
        }
      }
    } catch (err) {
      toast(`재생성을 시작하지 못했습니다: ${esc(err.message)}`, 'err');
    }
    await load();
  }

  async function resolveDup(d, action) {
    const dup = d.draft_meta.duplicates[0];
    const target = targets[dup.case_id];
    try {
      await api.resolveDuplicate(state.suite, d.case_id, { rev: d.rev, action, target_case_id: dup.case_id, target_rev: target.rev });
      toast({ update: `${dup.case_id}를 초안 내용으로 갱신했습니다`, skip: '초안을 반려했습니다', add: '중복이 아닌 것으로 표시했습니다' }[action], 'ok');
      await load();
      await NS.refreshCounts();
    } catch (err) {
      toast(err.status === 409 ? '다른 곳에서 먼저 바뀌었습니다. 목록을 새로 불러왔습니다.' : esc(err.message), 'err');
      await load();
    }
  }

  function bind() {
    $$('#drafts .dcard', root).forEach((el) => {
      const d = drafts[+el.dataset.i];
      el.addEventListener('click', (e) => { if (!e.target.closest('button,textarea')) setFocus(+el.dataset.i); });
      $('[data-id="draft-approve"]', el).addEventListener('click', () => decide(d, 'approved'));
      $('[data-id="draft-reject"]', el).addEventListener('click', () => decide(d, 'rejected'));
      $('[data-id="draft-edit"]', el).addEventListener('click', () => { NS.show('library'); NS.detail.open(d.case_id); });
      $('[data-id="draft-regen"]', el).addEventListener('click', () => { $('[data-regen]', el).hidden = false; $('textarea', el).focus(); });
      $('[data-id="draft-regen-cancel"]', el).addEventListener('click', () => { $('[data-regen]', el).hidden = true; });
      $('[data-id="draft-regen-submit"]', el).addEventListener('click', (e) => regenerate(d, $('textarea', el).value.trim(), e.target));
      $('[data-id="draft-source-ref"]', el).addEventListener('click', () => setFocus(+el.dataset.i));
      $$('[data-id^="dup-"]', el).forEach((b) => b.addEventListener('click', () => resolveDup(d, b.dataset.v)));
    });
  }

  async function setFocus(i) {
    if (!$(`#drafts .dcard[data-i="${i}"]`, root)) return;
    focus = i;
    $$('#drafts .dcard', root).forEach((el) => el.classList.toggle('focus', +el.dataset.i === i));
    $$('[data-review-index]', root).forEach(button => {
      button.classList.toggle('selected', +button.dataset.reviewIndex === i);
      button.setAttribute('aria-pressed', +button.dataset.reviewIndex === i);
    });
    const el = $(`#drafts .dcard[data-i="${i}"]`, root);
    if (el) el.focus({ preventScroll: false });
    await showSource();
  }

  async function showSource() {
    const seq = ++sourceSeq;
    const d = drafts[focus];
    const ref = d && d.source_refs[0];
    const box = $('#rv-excerpt', root);
    $('#rv-ref', root).textContent = ref || '';
    if (!ref || !jobInfo) { box.innerHTML = '<span class="faint">이 초안의 원문을 찾을 수 없습니다 (작업 정보 없음)</span>'; return; }
    try {
      const ex = await api.excerpt(jobInfo.job.bundle_id, ref);
      if (seq !== sourceSeq) return;
      let text = esc(ex.markdown);
      const quote = d.draft_meta.source_quote && esc(d.draft_meta.source_quote);
      if (quote && text.includes(quote)) text = text.replace(quote, `<mark>${quote}</mark>`);
      const entry = manifest && [...manifest.sources, ...(manifest.removed || [])].find((s) => ref.startsWith(s.ref));
      const frames = NS.sourceWatch && entry ? NS.sourceWatch.figmaFrames(jobInfo.job.bundle_id, entry) : '';
      box.innerHTML = `<h5>${esc(ex.title)} › ${esc(ex.section)} (${esc(ex.anchor)})</h5>${frames}<div style="white-space:pre-wrap">${text}</div>`;
    } catch (err) {
      if (seq !== sourceSeq) return;
      box.innerHTML = `<span class="faint">원문을 불러오지 못했습니다: ${esc(err.message)}</span>`;
    }
  }

  async function loadGaps() {
    const t = jobInfo ? jobInfo.job.target : (drafts[0] ? { sheet: drafts[0].sheet, path: drafts[0].path } : null);
    const list = $('#rv-gaps', root);
    if (!t) { list.innerHTML = '<li class="faint">대상 가지가 없습니다</li>'; return; }
    const profile = jobInfo ? jobInfo.job.profile : '기본';
    $('#rv-cov-profile', root).textContent = `${profile} 프로필 기준`;
    const { features } = await api.coverage(state.suite, t.sheet, t.path.filter(Boolean), profile);
    // 이번 초안의 기능을 먼저 보이고, 같은 가지의 나머지 기능은 접어 둔다 (가지 전체가 빨간 막대로 쏟아지지 않게)
    const mine = new Set(drafts.map((d) => d.feature));
    const related = features.filter((f) => mine.has(f.feature));
    const rest = related.length ? features.filter((f) => !mine.has(f.feature)) : features;
    const item = (f) => `<li><div><b>${esc(f.feature)}</b><div class="help">정상 ${f.positive} · 예외 ${f.negative} · 유효성 ${f.has_input ? f.validation : '해당 없음'}${f.missing.length ? ` · 부족: ${f.missing.join(', ')}` : ''}</div></div>
      <span class="row"><span class="meter" title="왼쪽 정상 · 오른쪽 예외 (빨강 = 없음)"><i class="${f.positive ? 'on' : 'miss'}"></i><i class="${f.negative ? 'on' : 'miss'}"></i></span>${f.missing.length ? '<button class="btn-sm" data-id="coverage-generate-more">더 생성</button>' : ''}</span></li>`;
    list.innerHTML = (related.length ? related.map(item).join('') + (rest.length
      ? `<li class="gap-more"><details data-id="coverage-others"><summary class="faint">같은 가지의 다른 기능 ${rest.length}개</summary><ul class="gap-list">${rest.map(item).join('')}</ul></details></li>` : '')
      : rest.map(item).join(''))
      || '<li class="faint">이 가지에 케이스가 없습니다</li>';
    $$('[data-id="coverage-generate-more"]', list).forEach((b) => b.addEventListener('click', () => {
      NS.show('generate');
      NS.generateView.prefill({ sheet: t.sheet, path: t.path });
      toast('대상 가지를 채워 두었습니다. 부족한 케이스를 설명하는 소스를 넣고 초안 생성을 누르세요.', '');
    }));
  }

  async function approveClean() {
    const clean = drafts.filter((d) => pending(d) && !d.has_error && !unresolvedDup(d) && !estimated(d) && !styleIssues(d).length);
    if (!clean.length) { toast('일괄 승인할 초안이 없습니다.', ''); return; }
    const res = await api.bulk(state.suite, clean.map((d) => ({ case_id: d.case_id, rev: d.rev })), 'set', 'status', 'approved');
    const left = drafts.filter(pending).length - res.updated.length;
    toast(`문제없는 초안 ${res.updated.length}건을 승인했습니다. 남은 ${left}건은 직접 확인하세요.`, 'ok');
    await load();
    await NS.refreshCounts();
  }

  function onShow() { load(); }

  function mount(r) {
    root = r;
    $$('[data-id="review-filter"] button', root).forEach((b) => b.addEventListener('click', () => {
      filter = b.dataset.f;
      $$('[data-id="review-filter"] button', root).forEach((x) => x.setAttribute('aria-pressed', x === b));
      render();
      showSource();
    }));
    $('#review-approve-clean', root).addEventListener('click', approveClean);
    document.addEventListener('keydown', (e) => {
      if (state.screen !== 'review' || e.target.closest('input,textarea,select') || e.metaKey || e.ctrlKey || !drafts.length) return;
      const k = e.key.toLowerCase();
      const visible = $$('[data-review-index]', root).map(button => +button.dataset.reviewIndex);
      const position = visible.indexOf(focus);
      if (position < 0) return;
      if (k === 'j') setFocus(visible[Math.min(position + 1, visible.length - 1)]);
      else if (k === 'k') setFocus(visible[Math.max(position - 1, 0)]);
      else if (k === 'a' || k === 'r') {
        const action = k === 'a' ? 'draft-approve' : 'draft-reject';
        const button = $(`.dcard[data-i="${focus}"] [data-id="${action}"]`, root);
        if (button && !button.disabled) button.click();
      }
      else if (k === 'g') { e.preventDefault(); const b = $(`.dcard[data-i="${focus}"] [data-id="draft-regen"]`, root); if (b && !b.disabled) b.click(); }
      else if (k === 'e') $(`.dcard[data-i="${focus}"] [data-id="draft-edit"]`, root)?.click();
    });
  }
})(window.TCS_NS = window.TCS_NS || {});
