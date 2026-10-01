// TC 스튜디오 — 원격 소스(PRD URL·Confluence·Figma) 탭, 연결 설정, 출처 변경 배너 (PRD F1.3, F1.4, F5.9, §7)
// generate.js의 registerSourceTab()과 library.js의 sourceWatch 훅에 붙는다. generate.js 다음, main.js 전에 로드.
(function (NS) {
  'use strict';

  const { state, api, esc, $, $$, toast } = NS;
  let creds = { confluence: { configured: false }, figma: { configured: false } };

  function urlTab(id, label, placeholder, help, run, extra = '') {
    NS.generateView.registerSourceTab({
      id, label,
      html: () => `<div class="field"><div class="row" style="flex-wrap:nowrap">
          <input class="input" id="src-${id}-url" data-id="src-${id}-url" placeholder="${esc(placeholder)}" autocomplete="off" aria-label="${esc(label)} 주소">
          <button class="btn btn-ghost" data-id="src-${id}-fetch" id="src-${id}-fetch">수집</button></div>
        ${extra}<span class="help">${help}</span></div>`,
      mount: (r, add) => {
        const input = $(`#src-${id}-url`, r);
        const go = async () => {
          const url = input.value.trim();
          if (!/^https?:\/\//.test(url)) { input.classList.add('error'); toast('주소를 https://로 시작하게 넣어 주세요.', 'err'); return; }
          input.classList.remove('error');
          const btn = $(`#src-${id}-fetch`, r);
          btn.classList.add('loading');
          btn.disabled = true;
          try {
            if (await run(add, url, r)) input.value = '';
          } finally {
            btn.classList.remove('loading');
            btn.disabled = false;
          }
        };
        $(`#src-${id}-fetch`, r).addEventListener('click', go);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
      },
    });
  }

  urlTab('url', 'PRD URL', 'https://docs.example.com/product/prd 또는 PDF 문서 주소',
    '공개 HTTPS 문서(HTML·PDF·DOCX·Markdown·텍스트). 로그인이 필요한 문서는 Confluence 연결이나 파일 업로드를 쓰세요. 내부망 주소는 막습니다.',
    (add, url) => add((id) => api.addSourceUrl(id, url)));

  urlTab('confluence', 'Confluence', 'https://회사.atlassian.net/wiki/spaces/…/pages/48213377/…',
    'Cloud: /wiki/spaces/…/pages/{id}, viewpage.action?pageId=, /x/{tiny} · Server/DC: 연결 설정에서 base URL 지정',
    async (add, url, r) => {
      if (!creds.confluence.configured) { openSettings('confluence'); return false; }
      const children = $('#src-confluence-children', r).checked;
      try {
        const id = await NS.generateView.ensureBundle();
        const { sources } = await api.addSourceConfluence(id, url, children);
        sources.forEach((s) => NS.generateView.pushSource(s));
        toast(`Confluence 페이지 ${sources.length}개를 가져왔습니다 (${esc(sources[0].version)})`, 'ok', [], 2500);
        return true;
      } catch (err) {
        toast(`가져오지 못했습니다: ${esc(err.message)}`, 'err');
        return false;
      }
    },
    '<label class="row help"><input type="checkbox" id="src-confluence-children" data-id="src-confluence-children"> 하위 페이지 포함 (깊이 1, 최대 20개)</label>');

  urlTab('figma', 'Figma', 'https://www.figma.com/design/{fileKey}/…?node-id=12-345',
    'node-id가 있으면 그 프레임만, 없으면 상위 프레임 최대 10개. 화면 문구는 "확인된 문구"로 들어갑니다.',
    async (add, url) => {
      if (!creds.figma.configured) { openSettings('figma'); return false; }
      return add((id) => api.addSourceFigma(id, url));
    });

  // ── 연결 상태 · 설정 ─────────────────────────────────────────
  function credHtml() {
    const c = creds.confluence;
    return `<span class="tag ${c.configured ? 'ok' : ''}" data-id="cred-status-confluence">${c.configured ? `Confluence 연결됨 · ${esc(c.email_masked || c.base_url)}` : 'Confluence 미연결'}</span>
      <span class="tag ${creds.figma.configured ? 'ok' : ''}" data-id="cred-status-figma">${creds.figma.configured ? 'Figma 연결됨' : 'Figma 미연결'}</span>
      <button class="btn-sm" data-id="cred-settings" id="cred-settings">연결 설정</button>`;
  }

  async function loadCreds() {
    creds = await api.credentials();
    const box = $('#src-extra');
    if (!box) return;
    box.innerHTML = `<div class="cred">${credHtml()}</div>`;
    $('#cred-settings', box).addEventListener('click', () => openSettings('confluence'));
  }

  function openSettings(kind) {
    const scrim = $('#cred-modal');
    const c = creds.confluence;
    $('#cred-base', scrim).value = c.base_url || '';
    $('#cred-email', scrim).value = '';
    $('#cred-email', scrim).placeholder = c.email_masked || 'qa@회사.com';
    $('#cred-deployment', scrim).value = c.deployment || 'cloud';
    $('#cred-conf-token', scrim).value = '';
    $('#cred-figma-token', scrim).value = '';
    scrim.hidden = false;
    $(kind === 'figma' ? '#cred-figma-token' : '#cred-base', scrim).focus();
  }

  function modalHtml() {
    return `<div class="scrim" id="cred-modal" data-id="cred-modal" hidden>
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="cred-title" style="width:min(480px,100%)">
        <div class="panel-head"><span id="cred-title">연결 설정</span><span class="spacer"></span><button class="icon-btn" data-id="cred-close" id="cred-close" aria-label="닫기">✕</button></div>
        <div class="panel-body" style="display:grid;gap:10px">
          <b>Confluence</b>
          <label class="field">base URL<input class="input" id="cred-base" data-id="cred-base" placeholder="https://회사.atlassian.net"></label>
          <div class="row"><label class="field" style="flex:1">이메일 (Cloud)<input class="input" id="cred-email" data-id="cred-email"></label>
            <label class="field">배포<select class="select" id="cred-deployment" data-id="cred-deployment"><option value="cloud">Cloud (이메일+API 토큰)</option><option value="dc">Server/DC (개인 액세스 토큰)</option></select></label></div>
          <label class="field">토큰<input class="input" type="password" id="cred-conf-token" data-id="cred-conf-token" placeholder="비워 두면 기존 토큰 유지" autocomplete="off"></label>
          <b>Figma</b>
          <label class="field">개인 액세스 토큰<input class="input" type="password" id="cred-figma-token" data-id="cred-figma-token" placeholder="비워 두면 기존 토큰 유지" autocomplete="off"></label>
          <span class="help">토큰은 서버의 config/*_config.json(git 제외)에만 저장되고 다시 보여 주지 않습니다.</span>
          <div class="row"><span class="spacer"></span><button class="btn btn-ghost" id="cred-cancel" data-id="cred-cancel">취소</button><button class="btn btn-primary" id="cred-save" data-id="cred-save">저장</button></div>
        </div></div></div>`;
  }

  async function saveSettings() {
    const scrim = $('#cred-modal');
    try {
      const base = $('#cred-base', scrim).value.trim();
      const email = $('#cred-email', scrim).value.trim();
      const confToken = $('#cred-conf-token', scrim).value.trim();
      if (base || email || confToken) {
        await api.saveCredentials('confluence', { base_url: base, deployment: $('#cred-deployment', scrim).value,
          ...(email ? { email } : {}), token: confToken });
      }
      const figmaToken = $('#cred-figma-token', scrim).value.trim();
      if (figmaToken) await api.saveCredentials('figma', { token: figmaToken });
      scrim.hidden = true;
      toast('연결 설정을 저장했습니다.', 'ok');
      await loadCreds();
    } catch (err) {
      toast(`저장하지 못했습니다: ${esc(err.message)}`, 'err');
    }
  }

  // ── 출처 변경 배너 (라이브러리) ──────────────────────────────
  NS.sourceWatch = {
    async renderBanner(root) {
      const box = $('#lib-banners', root);
      if (!box || !state.suite) return;
      const { changes } = await api.sourceChanges(state.suite);
      const count = changes.reduce((n, c) => n + c.case_ids.length, 0);
      $('#n-review', root).textContent = count;
      box.innerHTML = changes.length ? `<div class="banner warn" data-id="banner-source-changed"><b>출처 문서가 바뀌었습니다</b>
        <span>${changes.map((c) => `${esc(c.ref.split('@')[0])} ${esc(c.from)} → ${esc(c.to)}`).join(' · ')} · 관련 케이스 ${count}건이 재검토 필요 상태입니다.</span>
        <span class="spacer"></span><button class="btn-sm" data-id="banner-review-now" id="banner-review-now">${count}건만 보기</button></div>` : '';
      const b = $('#banner-review-now', box);
      if (b) b.addEventListener('click', () => { const chip = $('#lib-filter-needs-review', root); if (chip.getAttribute('aria-pressed') !== 'true') chip.click(); });
    },
    async scan(root) {
      const btn = $('#btn-check-sources', root);
      btn.classList.add('loading');
      btn.disabled = true;
      try {
        const res = await api.scanSources(state.suite);
        const errs = res.errors.length ? ` · 확인 실패 ${res.errors.length}건 (${esc(res.errors[0].error)})` : '';
        toast(res.changes.length ? `출처 ${res.changes.length}개가 바뀌었습니다${errs}` : `출처 ${res.checked}개 모두 최신입니다${errs}`, res.changes.length || res.errors.length ? 'warn' : 'ok');
        await NS.library.refresh();
      } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
      }
    },
  };

  // 상세 패널 원문 탭: 바뀐 출처의 차이 + 확인 완료 (detail.js가 부른다)
  NS.sourceWatch.detailSource = async function (box, c, onAck) {
    const change = (c.flags || {}).source_change;
    if (!change) return;
    const ref = c.source_refs.find((r) => r.startsWith(change.ref)) || change.ref;
    box.insertAdjacentHTML('beforeend', `<div class="warnbox" data-id="detail-source-diff"><b>${esc(change.from)} → ${esc(change.to)}에서 바뀐 부분</b><div class="diff" id="d-diff">불러오는 중…</div>
      <div class="row"><button class="btn-sm" data-id="detail-mark-reviewed" id="detail-mark-reviewed">변경 확인 완료</button></div></div>`);
    $('#detail-mark-reviewed', box).addEventListener('click', onAck);
    try {
      const { lines, old_available: old } = await api.sourceDiff(ref);
      $('#d-diff', box).innerHTML = (old ? '' : '<div class="faint">옛 본문이 없어 새 본문만 보여 줍니다</div>')
        + lines.filter((l) => l.op !== ' ').slice(0, 60).map((l) => (l.op === '-' ? `<del>${esc(l.text)}</del>` : l.op === '+' ? `<ins>${esc(l.text)}</ins>` : '<span class="faint">…</span>')).join('<br>');
    } catch (err) {
      $('#d-diff', box).textContent = `차이를 불러오지 못했습니다: ${err.message}`;
    }
  };

  // 초안 검토 원문 패널: Figma 출처면 프레임 이미지 (review.js가 부른다)
  NS.sourceWatch.figmaFrames = function (bundleId, entry) {
    if (!entry || entry.kind !== 'figma' || !(entry.assets || []).length) return '';
    return `<div class="figma-shots" data-id="source-figma-frame">${entry.assets.map((a) =>
      `<img src="/api/tc-library/sources/${encodeURIComponent(bundleId)}/assets/${encodeURIComponent(a)}" alt="${esc(entry.title)} 프레임" style="max-width:100%;border-radius:12px;border:1px solid var(--line)">`).join('')}</div>`;
  };

  // generate 화면이 그려진 뒤 연결 상태와 설정 창을 붙인다
  const origMount = NS.generateView.mount;
  NS.generateView.mount = function (root) {
    origMount(root);
    root.querySelector('.tc-studio').insertAdjacentHTML('beforeend', modalHtml());
    const scrim = $('#cred-modal');
    ['#cred-close', '#cred-cancel'].forEach((s) => $(s, scrim).addEventListener('click', () => { scrim.hidden = true; }));
    $('#cred-save', scrim).addEventListener('click', saveSettings);
    loadCreds();
  };
})(window.TCS_NS = window.TCS_NS || {});
