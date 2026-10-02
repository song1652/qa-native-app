// TC 스튜디오 — 내보내기 화면 (Phase 1: 엑셀 카드만. md 카드는 Phase 4) (PRD F6)
(function (NS) {
  'use strict';

  const { state, api, esc, $, $$, toast } = NS;
  let root = null;
  let lastExport = null;

  NS.exportView = { html, mount, onShow };

  function html() {
    return `
  <section class="screen" id="screen-export" data-screen="export">
    <div class="wrap">
      <div class="exp">
        <div class="panel exp-card" style="padding:16px">
          <div class="head"><div class="fmt xl">XLSX</div><div><b style="font-size:14px">엑셀로 내보내기</b>
            <div class="help">가져온 템플릿의 사본에 계층 순서대로 씁니다. 원본 파일은 바꾸지 않습니다.</div></div></div>
          <div class="field"><span class="label">범위</span>
            <div class="radio-list" data-id="xlsx-scope">
              <label class="radio"><input type="radio" name="xscope" value="all" checked> 전체 <span class="n" id="x-all-n"></span></label>
              <label class="radio"><input type="radio" name="xscope" value="sheets"> 선택한 시트 <span class="n" id="x-sheets-n"></span></label>
              <div class="sheet-picks" id="xlsx-sheets" data-id="xlsx-sheets" role="group" aria-label="내보낼 시트" hidden></div>
              <label class="radio"><input type="radio" name="xscope" value="case_ids"> 현재 필터 결과 <span class="n" id="x-filter-n"></span></label>
              <label class="radio"><input type="radio" name="xscope" value="approved"> 승인된 케이스만 <span class="n" id="x-approved-n" data-id="xlsx-approved-note"></span></label>
            </div></div>
          <div class="warnbox" data-id="xlsx-openpyxl-warning"><b>다시 저장하면 사라질 수 있는 요소</b>
            <span>이미지·차트와 일부 조건부서식은 사본에서 빠질 수 있습니다. 검사 결과를 확인한 뒤 내려받으세요.</span></div>
          <div class="field"><span class="label">무결성 검사</span>
            <ul class="checks" id="xlsx-checks" data-id="xlsx-integrity"><li class="faint">내보내기 전에 검사를 실행하세요</li></ul>
            <button class="btn btn-ghost" data-id="xlsx-run-check" id="xlsx-run-check" style="justify-self:start">검사 실행</button></div>
          <div class="field"><span class="label">History 시트에 추가할 행</span>
            <textarea class="textarea" id="xlsx-history-note" data-id="xlsx-history-note" rows="3"></textarea></div>
          <div class="field"><span class="label">파일 이름</span><div class="fname" id="xlsx-filename" data-id="xlsx-filename">—</div></div>
          <button class="btn btn-primary" data-id="xlsx-download" id="xlsx-download" disabled style="justify-self:start">검사 후 내려받기</button>
        </div>
        ${mdCardHtml()}
      </div>
      <div class="md-preview" id="md-preview-panel" data-id="md-preview-panel" hidden></div>
    </div>
  </section>`;
  }

  // ── md 카드 (Phase 4, 목업 797~845행) ──────────────────────
  let mdRun = null;

  function mdCardHtml() {
    return `<div class="panel exp-card" style="padding:16px" data-id="md-card">
      <div class="head"><div class="fmt md">.md</div><div><b style="font-size:14px">파이프라인용 md로 내보내기</b>
        <div class="help">승인 · 추정 문구 없음 · 그룹 매핑된 케이스만 testcases/에 씁니다. 반영 이력에서 내용을 확인하고 되돌릴 수 있습니다.</div></div></div>
      <div class="field"><span class="label">대상 조건</span><div class="funnel" data-id="md-eligibility" id="md-funnel"></div></div>
      <div class="field"><span class="label">그룹 매핑 (앱 testcases 폴더)</span><div data-id="md-group-map" id="md-groups"></div></div>
      <div class="warnbox" data-id="md-drift-warning" id="md-drift" hidden></div>
      <details data-id="md-excluded-list" id="md-excluded"></details>
      <div class="row"><button class="btn btn-primary" data-id="md-preview" id="md-preview">md 미리보기</button><span class="help" id="md-preview-hint"></span></div>

    </div>`;
  }

  async function loadMd() {
    if (!state.suite) return;
    const el = await api.mdEligibility(state.suite);
    const max = Math.max(el.funnel[0].count, 1);
    $('#md-funnel', root).innerHTML = el.funnel.map((f) => `<div class="f"><span>${esc(f.label)}</span><span class="track"><i style="width:${(f.count / max) * 100}%"></i></span><span class="v">${f.count}</span></div>`).join('');
    $('#md-groups', root).innerHTML = el.branches.map((b, i) => `<div class="maprow"><span>${esc(b.path.join(' › '))} <span class="faint">→ ${b.group ? `${esc(b.group)} (${esc(b.code)})` : '(없음)'}</span></span>
      ${b.group ? `<span class="tag ok">매핑됨 · ${b.count}건</span>` : `<span class="row"><span class="tag err">그룹 없음 · ${b.count}건 제외</span>
        <input class="input mono" data-id="md-map-group" data-i="${i}" placeholder="폴더명" style="width:130px">
        <input class="input mono" data-id="md-map-code" data-i="${i}" placeholder="접두어" maxlength="8" style="width:80px">
        <button class="btn-sm" data-id="md-map-fix" data-i="${i}">매핑 추가</button></span>`}</div>`).join('')
      || '<span class="help">승인된 케이스가 없습니다</span>';
    $$('[data-id="md-map-fix"]', root).forEach((b) => b.addEventListener('click', async () => {
      const i = b.dataset.i;
      try {
        await api.saveMdGroup(state.suite, el.branches[i].path, $(`[data-id="md-map-group"][data-i="${i}"]`, root).value,
          $(`[data-id="md-map-code"][data-i="${i}"]`, root).value.trim().toUpperCase());
        toast('그룹 매핑을 저장했습니다.', 'ok');
        await loadMd();
      } catch (err) { toast(`매핑하지 못했습니다: ${esc(err.message)}`, 'err'); }
    }));
    const drift = $('#md-drift', root);
    drift.hidden = !el.drifted.length;
    drift.innerHTML = el.drifted.length ? `<b>testcases/에서 직접 바뀐 파일 ${el.drifted.length}개</b>
      <span class="mono" style="font-size:11px">${el.drifted.map((d) => esc(d.file)).join(' · ')}</span>
      <span>라이브러리가 원본입니다. 미리보기에서 파일마다 건너뛰기 또는 덮어쓰기를 고릅니다.</span>` : '';
    $('#md-excluded', root).innerHTML = `<summary class="muted" style="cursor:pointer;font-size:12px">제외된 ${el.excluded.length}건 보기</summary>
      <ul class="checks" style="margin-top:8px">${el.excluded.map((x) => `<li><span class="wr">!</span>${esc(x.case_id)} ${esc(x.feature)} · ${esc(x.reason)}</li>`).join('')}</ul>`;
    $('#md-preview', root).disabled = !el.funnel[el.funnel.length - 1].count;
    $('#md-preview', root).textContent = `md 미리보기 (${el.funnel[el.funnel.length - 1].count}건)`;
  }

  const STATUS_TAG = { added: ['ok', '신규'], updated: ['info', '갱신'], conflict: ['warn', '충돌'], same: ['', '동일'], error: ['err', '오류'] };

  function pipelineLinks(paths) {
    const targets = [...new Set(paths.map((file) => file.split('/').slice(0, 2).join('/')))]
      .filter((target) => /^(android|ios)\/[A-Za-z0-9_-]+$/.test(target));
    return targets.map((target) => {
      const [platform, folder] = target.split('/');
      const href = `/?view=pipeline&from_tc_studio=1&platform=${encodeURIComponent(platform)}&tc_folder=${encodeURIComponent(folder)}`;
      return `<a class="btn btn-primary" data-id="md-pipeline-link" href="${href}">${esc(folder)} 파이프라인 실행 →</a>`;
    }).join(' ');
  }

  function renderMdPreview() {
    const s = mdRun.summary;
    const conflicts = mdRun.rows.filter((r) => r.status === 'conflict');
    $('#md-preview-panel', root).hidden = false;
    $('#md-preview-panel', root).innerHTML = `<div class="row"><b>md 변경 미리보기</b><span class="tag info mono">${esc(mdRun.run_id)}</span></div>
      <div class="row">${Object.entries(STATUS_TAG).map(([k, [cls, l]]) => `<span class="tag ${cls}">${l} ${s[k] || 0}</span>`).join('')}</div>
      <div style="overflow-x:auto"><table aria-label="md 내보내기 미리보기"><thead><tr><th>상태</th><th>케이스 / 대상 파일</th><th>이유</th><th>처리</th></tr></thead><tbody>
      ${mdRun.rows.map((r) => `<tr><td><span class="tag ${STATUS_TAG[r.status][0]}">${STATUS_TAG[r.status][1]}</span></td><td class="mono">${esc(r.case_id)} · ${esc(r.file)}</td><td>${esc(r.reason)}</td>
        <td>${r.status === 'conflict' ? `<select class="select md-conflict-decision" data-id="md-conflict-decision" data-tc="${esc(r.file)}" aria-label="${esc(r.file)} 충돌 처리"><option value="">기본: 건너뛰기</option><option value="skip">건너뛰기</option><option value="overwrite">라이브러리 값으로 덮어쓰기</option></select>` : r.excluded ? '반영 안 함' : '자동'}</td></tr>`).join('')}
      </tbody></table></div>
      <div class="row"><button class="btn btn-success" id="md-commit" data-id="md-commit">md 반영</button><span class="help" id="md-commit-hint"></span><span id="md-existing-pipeline">${pipelineLinks(mdRun.rows.filter((r) => ['same', 'updated', 'conflict'].includes(r.status)).map((r) => r.file))}</span></div>
      <div id="md-result" hidden class="row"><span class="tag ok" id="md-result-text"></span><span id="md-run-links"></span><button class="btn btn-ghost" id="md-rollback" data-id="md-rollback">이 작업 롤백</button></div>`;
    $('#md-preview-panel', root).insertAdjacentHTML('afterbegin', '<button class="btn btn-ghost" id="md-preview-back">← 내보내기</button>');
    $('#md-preview-back', root).addEventListener('click', () => { $('#md-preview-panel', root).hidden = true; $('#md-preview', root).focus(); });
    const update = () => {
      const pending = $$('.md-conflict-decision', root).filter((x) => !x.value).length;
      $('#md-commit', root).disabled = false;
      $('#md-commit-hint', root).textContent = pending ? `미결정 충돌 ${pending}건은 기존 파일을 보존합니다` : '';
    };
    $$('.md-conflict-decision', root).forEach((x) => x.addEventListener('change', update));
    update();
    $('#md-commit', root).addEventListener('click', async () => {
      const skip = $$('.md-conflict-decision', root).filter((x) => x.value !== 'overwrite').map((x) => x.dataset.tc);
      const overwrite = $$('.md-conflict-decision', root).some((x) => x.value === 'overwrite');
      try {
        const res = await api.mdCommit(state.suite, mdRun.run_id, skip, overwrite);
        $('#md-commit', root).disabled = true;
        $('#md-result', root).hidden = false;
        $('#md-result-text', root).textContent = `반영 완료 · 신규 ${res.created} · 갱신 ${res.updated}${skip.length ? ` · 건너뜀 ${skip.length}` : ''}`;
        $('#md-run-links', root).innerHTML = pipelineLinks(res.written || []);
        toast('md 파일을 반영했습니다. 필요하면 이 작업을 롤백할 수 있습니다.', 'ok');
        await loadMd();
      } catch (err) { toast(`반영하지 못했습니다: ${esc(err.message)}`, 'err'); }
    });
    $('#md-rollback', root).addEventListener('click', async () => {
      try {
        await api.mdRollback(state.suite, mdRun.run_id);
        $('#md-preview-panel', root).hidden = true;
        toast('이 작업의 md 변경을 되돌렸습니다.', 'ok');
        await loadMd();
      } catch (err) { toast(`롤백하지 못했습니다: ${esc(err.message)}`, 'err'); }
    });
  }

  function onShow() {
    $('#md-preview-panel', root).hidden = true;
    loadMd();
    lastExport = null;
    const suite = state.suites.find((s) => s.suite === state.suite);
    $('#x-all-n', root).textContent = suite ? suite.count : 0;
    $('#x-approved-n', root).textContent = suite && suite.imported ? `가져온 케이스 ${suite.imported}건 제외` : '';
    $('#x-filter-n', root).textContent = state.items.length;
    const counts = Object.fromEntries((state.tree || []).map((n) => [n.name, n.count]));
    $('#xlsx-sheets', root).innerHTML = (suite ? suite.sheets : []).map((s) => `<label class="sheet-pick"><input type="checkbox" value="${esc(s)}" checked>${esc(s)}<span class="n">${counts[s] ?? 0}</span></label>`).join('');
    syncSheets();
    const d = new Date();
    const yymmdd = `${String(d.getFullYear()).slice(2)}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
    if (!$('#xlsx-history-note', root).value) $('#xlsx-history-note', root).value = `${yymmdd} TC Studio 반영\n- `;
    resetCheck('');
  }

  function resetCheck(msg) {
    lastExport = null;
    $('#xlsx-download', root).disabled = true;
    $('#xlsx-download', root).textContent = '검사 후 내려받기';
    $('#xlsx-filename', root).textContent = '—';
    $('#xlsx-checks', root).innerHTML = `<li class="faint">${msg || '내보내기 전에 검사를 실행하세요'}</li>`;
  }

  const pickedSheets = () => $$('#xlsx-sheets input:checked', root).map((i) => i.value);
  // 시트 목록은 '선택한 시트'일 때만 펼치고, 하나도 고르지 않으면 검사를 막는다
  function syncSheets() {
    const scope = $('input[name="xscope"]:checked', root).value;
    const total = $$('#xlsx-sheets input', root).length, picked = pickedSheets().length;
    $('#xlsx-sheets', root).hidden = scope !== 'sheets';
    $('#x-sheets-n', root).textContent = `${picked}/${total}개`;
    $('#xlsx-run-check', root).disabled = scope === 'sheets' && !picked;
  }

  function payload() {
    const scope = $('input[name="xscope"]:checked', root).value;
    const body = { scope, history_note: $('#xlsx-history-note', root).value.trim() };
    if (scope === 'sheets') body.sheets = pickedSheets();
    if (scope === 'case_ids') body.case_ids = state.items.map((c) => c.case_id);
    return body;
  }

  async function runCheck(e) {
    const btn = e.currentTarget;
    btn.classList.add('loading');
    btn.disabled = true;
    $('#xlsx-checks', root).innerHTML = '<li class="faint">사본에 쓰고 다시 여는 중…</li>';
    try {
      lastExport = await api.exportXlsx(state.suite, payload());
      $('#xlsx-checks', root).innerHTML = lastExport.checks.map((c) =>
        `<li><span class="${c.level === 'ok' ? 'ok' : 'bad'}">${c.level === 'ok' ? '✓' : '✕'}</span>${esc(c.message)}</li>`).join('');
      $('#xlsx-filename', root).textContent = lastExport.filename;
      const ok = lastExport.checks.every((c) => c.level === 'ok');
      $('#xlsx-download', root).disabled = false;
      $('#xlsx-download', root).textContent = ok ? `내려받기 (${lastExport.count}건)` : '오류가 있지만 내려받기';
    } catch (err) {
      resetCheck(`검사 실패: ${esc(err.message)}`);
    } finally {
      btn.classList.remove('loading');
      btn.disabled = false;
    }
  }

  function mount(r) {
    root = r;
    $$('input[name="xscope"]', root).forEach((i) => i.addEventListener('change', () => { syncSheets(); resetCheck('범위가 바뀌었습니다. 검사를 다시 실행하세요'); }));
    $('#xlsx-sheets', root).addEventListener('change', () => { syncSheets(); resetCheck('범위가 바뀌었습니다. 검사를 다시 실행하세요'); });
    $('#xlsx-run-check', root).addEventListener('click', runCheck);
    $('#md-preview', root).addEventListener('click', async () => {
      try {
        mdRun = await api.mdPreview(state.suite);
        renderMdPreview();
        const conflicts = mdRun.rows.filter((r) => r.status === 'conflict').length;
        toast(conflicts ? `md 미리보기를 만들었습니다. 충돌 ${conflicts}건의 처리 방법을 고르세요.` : 'md 미리보기를 만들었습니다.', '');
      } catch (err) { toast(`미리보기를 만들지 못했습니다: ${esc(err.message)}`, 'err'); }
    });
    $('#xlsx-download', root).addEventListener('click', () => {
      if (!lastExport) return;
      const a = document.createElement('a');
      a.href = api.downloadUrl(lastExport.export_id);
      a.download = lastExport.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast(`${esc(lastExport.filename)} 파일을 내려받습니다.`, 'ok');
    });
  }
})(window.TCS_NS = window.TCS_NS || {});
