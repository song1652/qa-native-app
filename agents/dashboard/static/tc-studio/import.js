// TC 스튜디오 — Excel 가져오기·매핑·변경 확인·작업 이력
(function (NS) {
  'use strict';
  const { state, api, esc, $, $$, toast } = NS;
  let root, previews = [], files = [], profiles = [], plan = null, busy = false, generation = 0, planVersion = 0, mappingDirty = false;
  const fields = [['header_row','헤더 행','1'],['source_tc_id','원본 TC ID',''],['feature','제목*','B'],['steps','Step*','C'],['expected','Expected*','D'],['precondition','사전 조건',''],['l1','대분류',''],['l2','중분류',''],['l3','소분류',''],['priority','우선순위',''],['tags','태그','']];
  const statuses = {new:'신규',updated:'갱신',same:'동일',conflict:'충돌',error:'오류',committed:'반영 완료',preview:'미리보기',preview_ready:'미리보기 준비',rolled_back:'되돌림'};
  NS.importModal = { html, mount, open };
  function html() {
    return `<div class="scrim" id="import-modal" data-id="import-modal" hidden>
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="im-title" style="width:min(900px,96vw)">
      <div class="panel-head"><span id="im-title">엑셀을 라이브러리로 가져오기</span><span class="spacer"></span><button class="icon-btn" id="import-close" data-id="import-close" aria-label="닫기">✕</button></div>
      <div class="panel-body" style="display:grid;gap:12px;max-height:82vh;overflow:auto">
        <div class="row"><span class="help">파일 선택 → 열 매핑 → 변경 확인 → 가져오기</span><span class="spacer"></span><button class="btn-sm" data-id="import-history-open" id="import-history-open">가져오기 이력</button></div>
        <label class="drop" id="import-drop" data-id="import-pick-file" for="import-file"><b>엑셀 파일을 끌어다 놓거나 눌러서 선택</b><span class="faint">.xlsx · 파일당 최대 25MB · 여러 파일 선택 가능 · 원본은 변경하지 않습니다</span></label>
        <input type="file" id="import-file" data-id="import-file-input" accept=".xlsx" multiple hidden>
        <div class="field"><span class="label">양식 인식</span><select class="select" id="import-mapping-mode" data-id="import-mapping-mode"><option value="auto">기준 양식 자동 인식 (대분류·기능·Test Step·Expected Result 헤더)</option><option value="custom">다른 양식 직접 매핑</option></select></div>
        <div id="import-custom-mapping" data-id="import-column-mapping" hidden style="display:grid;gap:8px">
          <div class="row"><span class="label">열 매핑 프로필</span><select class="select" id="import-mapping-profile" data-id="import-mapping-profile"><option value="">직접 입력</option></select></div>
          <div class="row" style="flex-wrap:wrap">${fields.map(([k,l,v])=>`<label class="field" style="width:105px">${l}<input class="input mono" data-map="${k}" value="${v}" maxlength="${k==='header_row'?6:3}"></label>`).join('')}</div>
          <div class="row" style="flex-wrap:wrap"><input class="input" id="import-profile-name" placeholder="저장할 매핑 이름" maxlength="50" aria-label="매핑 프로필 이름"><button class="btn-sm" data-id="import-profile-save">새 프로필 저장</button><button class="btn-sm" data-id="import-profile-update" disabled>선택 프로필 수정</button><button class="btn-sm" data-id="import-profile-delete" disabled>선택 프로필 삭제</button><button class="btn-sm" id="import-mapping-apply" data-id="import-mapping-apply">매핑 적용</button></div>
          <span class="help">열은 A, B, C…로 지정합니다. 대분류가 없으면 시트 이름을 사용합니다. 원본 ID와 태그를 지정하면 보존됩니다.</span>
        </div>
        <div id="import-preview" hidden style="display:grid;gap:12px">
          <label class="field"><span class="label">스위트 이름</span><input class="input" id="import-suite" data-id="import-suite" placeholder="예: 회원등록" autocomplete="off"><span class="help">같은 원본 ID·출처는 기존 케이스와 연결합니다. 변경 내용은 반영 전에 확인합니다.</span></label>
          <div class="field"><span class="label">가져올 파일·시트 · case_id 접두어</span><div class="radio-list" id="import-sheets" data-id="import-sheets"></div></div>
          <ul class="checks" id="import-warnings" data-id="import-warnings"></ul>
        </div>
        <section id="import-plan-panel" hidden><b>반영할 변경 내용</b><div id="import-plan-rows" data-id="import-plan-rows" style="overflow:auto"></div></section>
        <section id="import-history-panel" hidden><div class="row"><b>가져오기·md 반영 이력</b><span class="spacer"></span><button class="btn-sm" id="import-history-back">가져오기로 돌아가기</button><button class="btn-sm" id="import-history-refresh">새로고침</button></div><div id="import-history-list" data-id="import-history-list"></div><div id="import-history-detail" data-id="import-history-detail" style="margin-top:12px"></div></section>
        <div class="row"><span class="help" id="import-summary"></span><span class="spacer"></span><button class="btn btn-ghost" id="import-cancel" data-id="import-cancel">취소</button><button class="btn btn-ghost" id="import-plan" data-id="import-plan" disabled>변경 미리보기</button><button class="btn btn-primary" id="import-confirm" data-id="import-confirm" disabled>가져오기</button></div>
      </div></div></div>`;
  }
  const close = () => { if (!busy) { generation++; $('#import-modal',root).hidden=true; } };
  function resetPlan() { planVersion++; plan=null; $('#import-plan-panel',root).hidden=true; $('#import-confirm',root).disabled=true; }
  function open() {
    generation++; previews=[];files=[];resetPlan();
    $('#import-suite',root).value=''; $('#import-file',root).value='';
    $('#import-preview',root).hidden=true; $('#import-history-panel',root).hidden=true;
    $('#import-summary',root).textContent=''; $('#import-plan',root).disabled=true;
    $('#import-modal',root).hidden=false;
    refreshProfiles().catch(err=>toast(`프로필을 읽지 못했습니다: ${esc(err.message)}`,'err'));
  }
  function mapping() {
    if ($('#import-mapping-mode',root).value!=='custom') return null;
    const columns={}; let header_row=1;
    $$('[data-map]',root).forEach(i=>{if(i.dataset.map==='header_row') header_row=Number(i.value)||1; else if(i.value.trim()) columns[i.dataset.map]=i.value.trim().toUpperCase();});
    return {header_row,columns};
  }
  async function refreshProfiles(selected='') {
    ({profiles}=await api.mappingProfiles());
    $('#import-mapping-profile',root).innerHTML='<option value="">직접 입력</option>'+profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    $('#import-mapping-profile',root).value=selected;
    const sheetSelects=$$('#import-sheets [data-sheet-profile]',root);
    sheetSelects.forEach(select=>{
      const previous=select.value;
      select.innerHTML='<option value="">현재 공통 매핑</option>'+profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
      select.value=profiles.some(p=>p.id===previous)?previous:'';
    });
    if(sheetSelects.length)updateSummary();
    profileButtons();
  }
  function profileButtons() {
    const selected=!!$('#import-mapping-profile',root).value;
    $('[data-id="import-profile-update"]',root).disabled=!selected;
    $('[data-id="import-profile-delete"]',root).disabled=!selected;
  }
  function setMapping(p) {
    const m=p.mapping||{header_row:1,columns:p.columns||{}};
    $$('[data-map]',root).forEach(i=>{i.value=i.dataset.map==='header_row'?m.header_row||1:m.columns[i.dataset.map]||'';});
    generation++; mappingDirty=true; $('#import-profile-name',root).value=p.name; resetPlan(); $('#import-plan',root).disabled=true;
  }
  async function manageProfile(action) {
    try {
      const id=$('#import-mapping-profile',root).value;
      if(action==='delete') {await api.deleteMappingProfile(id);await refreshProfiles();$('#import-profile-name',root).value='';}
      else {const payload={name:$('#import-profile-name',root).value.trim(),mapping:mapping()};const res=action==='save'?await api.saveMappingProfile(payload):await api.updateMappingProfile(id,payload);await refreshProfiles(res.profile.id);}
      toast('매핑 프로필을 저장했습니다.','ok');
    } catch(err){toast(`프로필을 변경하지 못했습니다: ${esc(err.message)}`,'err');}
  }
  async function pick(chosen) {
    if(!chosen.length)return;
    files=Array.from(chosen); const token=++generation, selectedMapping=mapping();resetPlan();previews=[];
    $('#import-preview',root).hidden=true; $('#import-plan',root).disabled=true;
    $('#import-summary',root).textContent='파일 분석 중…';
    const drop=$('#import-drop',root), idle=drop.dataset.idle??(drop.dataset.idle=drop.innerHTML);
    drop.classList.add('busy'); drop.setAttribute('aria-busy','true');
    try {
      for(const [i,file] of files.entries()){
        if(!/\.xlsx$/i.test(file.name)||file.size>25*1024*1024)throw new Error(`${file.name}: .xlsx, 25MB 이하 파일을 선택하세요`);
        drop.innerHTML=`<b class="analyzing" role="status" data-id="import-analyzing">파일 분석 중… ${files.length>1?`(${i+1}/${files.length})`:''}</b><span class="faint">${esc(file.name)} · 시트와 헤더를 읽고 있습니다</span>`;
        const preview=await api.importPreview(file,selectedMapping);if(token!==generation)return;previews.push(preview);
      }
      if(!$('#import-suite',root).value.trim())$('#import-suite',root).value=(state.suites.find(s=>s.suite===state.suite)||{protected:true}).protected?files[0].name.normalize('NFC').replace(/\.xlsx$/i,'').replace(/_?Full$/i,'').replace(/[^\w가-힣-]/g,'_'):state.suite;
      let index=0;
      $('#import-sheets',root).innerHTML=previews.map((p,pi)=>`<div style="margin-bottom:8px"><b>${esc(p.filename)}</b>${p.sheets.map(s=>{const n=++index;return `<div class="row" style="flex-wrap:wrap"><label class="radio"><input type="checkbox" data-sheet="${esc(s.name)}" data-file="${pi}" checked>${esc(s.name)} <span class="n">${s.cases}행 · 헤더 ${s.header_row}행</span></label><input class="input mono" data-prefix="${esc(s.name)}" data-file="${pi}" value="S${String(n).padStart(2,'0')}" maxlength="8" style="width:90px" aria-label="${esc(s.name)} 접두어"><select class="select" data-sheet-profile="${esc(s.name)}" data-file="${pi}" aria-label="${esc(s.name)} 시트별 매핑"><option value="">현재 공통 매핑</option>${profiles.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')}</select></div>`;}).join('')}</div>`).join('');
      $('#import-warnings',root).innerHTML=previews.flatMap(p=>p.sheets.flatMap(s=>s.warnings.map(w=>`<li>${esc(p.filename)} · ${esc(s.name)}: ${esc(w)}</li>`))).join('');
      mappingDirty=false; $('#import-preview',root).hidden=false;updateSummary();
    }catch(err){if(token!==generation)return;previews=[];$('#import-summary',root).textContent=err.message;toast(`분석 실패: ${esc(err.message)}`,'err');}
    finally{if(token===generation){drop.innerHTML=idle;drop.classList.remove('busy');drop.removeAttribute('aria-busy');}}
  }
  function selection() {
    const sources=previews.map((p,pi)=>{
      const sheets=$$('#import-sheets input[type=checkbox]',root).filter(c=>c.checked&&Number(c.dataset.file)===pi).map(c=>c.dataset.sheet);
      const prefixes={},sheet_mappings={};
      $$('#import-sheets input[data-prefix]',root).filter(i=>Number(i.dataset.file)===pi).forEach(i=>prefixes[i.dataset.prefix]=i.value.trim().toUpperCase());
      $$('#import-sheets [data-sheet-profile]',root).filter(i=>Number(i.dataset.file)===pi&&i.value).forEach(i=>{const p=profiles.find(p=>p.id===i.value);if(p)sheet_mappings[i.dataset.sheetProfile]=p.mapping||{header_row:1,columns:p.columns};});
      return {preview_id:p.preview_id,sheets,prefixes,sheet_mappings};
    }).filter(s=>s.sheets.length);
    return {suite:$('#import-suite',root).value.trim(),sources};
  }
  function updateSummary(keepPlan) {
    if(keepPlan!==true) resetPlan();const payload=selection();
    const count=payload.sources.reduce((n,s)=>n+previews.find(p=>p.preview_id===s.preview_id).sheets.filter(x=>s.sheets.includes(x.name)).reduce((n,x)=>n+x.cases,0),0);
    const valid=!mappingDirty&&previews.length&&payload.sources.length&&/^[\w가-힣-]+$/.test(payload.suite)&&!payload.suite.startsWith('_')&&payload.sources.every(s=>s.sheets.every(x=>/^[A-Z][A-Z0-9]{0,7}$/.test(s.prefixes[x])));
    $('#import-plan',root).disabled=!valid||busy;
    const noSheets=previews.length&&previews.every(p=>!p.sheets.length);
    $('#import-summary',root).textContent=valid?(plan?`${count}건 · 변경 내용을 확인한 뒤 가져오기를 누르세요`:`${count}건 · 변경 미리보기를 눌러 바뀌는 내용을 먼저 확인하세요`):noSheets?'인식된 시트가 없습니다. 헤더(대분류·기능·Step·Expected Result)를 찾지 못했습니다. 양식 인식에서 직접 매핑을 선택하세요':'스위트·시트·접두어를 확인하세요';
    $('#import-confirm',root).textContent=`${count}건 가져오기`;
    nextStep();
  }
  function caseText(c){
    if(!c)return '없음';if(typeof c==='string')return c;
    const fields=[['source_tc_id','원본 ID'],['tc_id','MD ID'],['feature','제목'],['title','제목'],
      ['sheet','시트'],['path','분류'],['group','그룹'],['precondition','사전 조건'],['steps','단계'],
      ['expected','기대 결과'],['bullets','UI 문구'],['priority','우선순위'],
      ['execution_result','실행 결과'],['status','검토 상태'],['tags','태그'],['note','메모']];
    return fields.filter(([key])=>key in c).map(([key,label])=>{
      const value=c[key];
      return `${label}: ${Array.isArray(value)?value.map(x=>typeof x==='object'?JSON.stringify(x):x).join(' · '):value??''}`;
    }).join('\n');
  }
  function rowsHtml(rows,decisions=false){
    return `<table style="width:100%;font-size:12px"><thead><tr><th>상태</th><th>시트 / 원본 ID</th><th>제목·변경 내용</th><th>처리</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${esc(statuses[r.status]||r.status||'')}</td><td>${esc(r.sheet||r.sheet_name||'')}<br>${esc(r.source_tc_id||r.tc_id||r.case_id||'')}</td><td>${esc(r.feature||r.title||r.after?.feature||'')}<div class="help">${esc(r.reason||'')}</div>${r.before||r.after?`<details><summary>내용 비교</summary><div class="row" style="align-items:start"><pre style="white-space:pre-wrap;flex:1">변경 전\n${esc(caseText(r.before))}</pre><pre style="white-space:pre-wrap;flex:1">변경 후\n${esc(caseText(r.after))}</pre></div></details>`:''}</td><td>${decisions&&r.status!=='same'?`<select class="select" data-decision="${i}"><option value="${r.status==='conflict'||r.status==='error'?'':'apply'}">${r.status==='conflict'||r.status==='error'?'선택 필요':'반영'}</option><option value="skip">건너뛰기</option>${r.status==='conflict'?'<option value="overwrite">라이브러리 값 갱신</option>':''}</select>`:'—'}</td></tr>`).join('')}</tbody></table>`;
  }
  async function makePlan(){
    busy=true;const version=planVersion;$('#import-plan',root).disabled=true;$('#import-confirm',root).disabled=true;
    try{const result=await api.importPlan(selection());if(version!==planVersion)return;plan=result;$('#import-plan-rows',root).innerHTML=rowsHtml(plan.rows,true);$('#import-plan-panel',root).hidden=false;$('#import-plan-panel',root).scrollIntoView({block:'start',behavior:'smooth'});updateCommit();}
    catch(err){toast(`미리보기 실패: ${esc(err.message)}`,'err');}
    finally{busy=false;updateSummary(true);}
  }
  function updateCommit(){ $('#import-confirm',root).disabled=!plan||$$('[data-decision]',root).some(s=>!s.value); nextStep(); }
  // 다음에 누를 버튼을 강조한다: 미리보기 전엔 '변경 미리보기', 미리보기 후엔 '가져오기'
  function nextStep(){
    const planBtn=$('#import-plan',root),confirmBtn=$('#import-confirm',root);
    planBtn.classList.toggle('btn-primary',!plan);planBtn.classList.toggle('btn-ghost',!!plan);
    confirmBtn.classList.toggle('btn-primary',!!plan);confirmBtn.classList.toggle('btn-ghost',!plan);
    confirmBtn.title=confirmBtn.disabled?(plan?'충돌 행마다 덮어쓰기 또는 제외를 선택하세요':'먼저 변경 미리보기로 바뀌는 내용을 확인하세요'):'';
  }
  async function confirm(){
    if(!plan||busy)return;busy=true;$('#import-confirm',root).disabled=true;
    try{
      const skip=[],overwrite=[];$$('[data-decision]',root).forEach(s=>{const r=plan.rows[Number(s.dataset.decision)];if(s.value==='skip')skip.push(r.case_id);if(s.value==='overwrite')overwrite.push(r.case_id);});
      const result=await api.importCommit({run_id:plan.run_id,skip,overwrite});
      busy=false;close();toast(`가져왔습니다 · 추가 ${result.created} · 갱신 ${result.updated} · 그대로 ${result.unchanged}`,'ok');await NS.reloadSuites(result.suite);
    }catch(err){toast(`가져오지 못했습니다: ${esc(err.message)}`,'err');busy=false;updateCommit();}
  }
  async function loadHistory(){
    $('#import-history-panel',root).hidden=false;$('#import-history-list',root).textContent='이력을 읽는 중…';
    try{
      const [library,md]=await Promise.all([api.importRuns(),api.mdImportRuns()]);
      const runs=[...library.runs.map(r=>({...r,kind:'library'})),...md.runs.map(r=>({...r,kind:'md'}))];
      $('#import-history-list',root).innerHTML=(runs.length?runs.map(r=>`<div class="row" style="padding:8px 0;border-bottom:1px solid var(--line)"><span>${r.kind==='library'?'Excel → 라이브러리':r.tc_library_suite?'TC → md':'기존 Excel → md'} · ${esc(r.suite||r.tc_library_suite||'')} · ${esc(statuses[r.status]||r.status||'')} <span class="faint">${esc(r.created_at||r.at||'')}</span></span><span class="spacer"></span><button class="btn-sm" data-action="view" data-run="${esc(r.run_id)}" data-kind="${r.kind}">내용 보기</button></div>`).join(''):'저장된 작업이 없습니다.')+[...(library.errors||[]),...(md.errors||[])].map(x=>`<div class="warnbox">${esc(x.run_id||'')} · ${esc(x.error||'기록을 읽을 수 없습니다')}</div>`).join('');
    }catch(err){$('#import-history-list',root).textContent=err.message;}
  }
  async function viewRun(id,kind){
    try{
      const result=kind==='library'?await api.importRun(id):await api.mdImportRun(id);const run=result.run||result;
      $('#import-history-detail',root).innerHTML=`<b>${esc(run.suite||run.tc_library_suite||'md 반영')} · ${esc(run.status||'')}</b>${rowsHtml(run.rows||[])}<div class="row">${run.status==='committed'?`<button class="btn btn-ghost" data-action="rollback" data-run="${esc(id)}" data-kind="${kind}">이 작업 되돌리기</button>`:''}<span class="help">이후 편집이 있으면 되돌리기를 중단하여 변경을 보호합니다.</span></div>`;
    }catch(err){toast(`이력 조회 실패: ${esc(err.message)}`,'err');}
  }
  function mount(r){
    root=r;const drop=$('#import-drop',root);
    ['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('over');}));
    ['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,()=>drop.classList.remove('over')));
    drop.addEventListener('drop',e=>{e.preventDefault();pick(e.dataTransfer.files);});
    $('#import-file',root).addEventListener('change',e=>pick(e.target.files));
    ['#import-close','#import-cancel'].forEach(s=>$(s,root).addEventListener('click',close));
    $('#import-plan',root).addEventListener('click',makePlan);$('#import-confirm',root).addEventListener('click',confirm);
    ['#import-suite','#import-sheets'].forEach(s=>$(s,root).addEventListener('input',updateSummary));
    $('#import-custom-mapping',root).addEventListener('input',()=>{generation++;mappingDirty=true;resetPlan();$('#import-plan',root).disabled=true;$('#import-summary',root).textContent='매핑 적용으로 파일을 다시 분석하세요';});
    $('#import-mapping-mode',root).addEventListener('change',async e=>{$('#import-custom-mapping',root).hidden=e.target.value!=='custom';if(files.length)await pick(files);});
    $('#import-mapping-profile',root).addEventListener('change',e=>{profileButtons();const p=profiles.find(p=>p.id===e.target.value);if(p)setMapping(p);});
    ['save','update','delete'].forEach(action=>$(`[data-id="import-profile-${action}"]`,root).addEventListener('click',()=>manageProfile(action)));
    $('#import-mapping-apply',root).addEventListener('click',()=>pick(files));
    $('#import-plan-rows',root).addEventListener('change',updateCommit);
    $('#import-history-back',root).addEventListener('click',()=>{$('#import-history-panel',root).hidden=true;});
    ['#import-history-open','#import-history-refresh'].forEach(s=>$(s,root).addEventListener('click',loadHistory));
    $('#import-history-list',root).addEventListener('click',e=>{const b=e.target.closest('[data-action="view"]');if(b)viewRun(b.dataset.run,b.dataset.kind);});
    $('#import-history-detail',root).addEventListener('click',async e=>{const b=e.target.closest('[data-action="rollback"]');if(!b)return;b.disabled=true;try{if(b.dataset.kind==='library')await api.rollbackImport(b.dataset.run);else await api.rollbackMdImport(b.dataset.run);await viewRun(b.dataset.run,b.dataset.kind);await loadHistory();await NS.reloadSuites(state.suite);}catch(err){toast(`되돌리지 못했습니다: ${esc(err.message)}`,'err');b.disabled=false;}});
  }
})(window.TCS_NS = window.TCS_NS || {});
