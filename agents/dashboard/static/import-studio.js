var IMPORT_FIELDS=[['tc_id','TC ID',true],['title','제목',true],['precondition','사전 조건',true],['steps','테스트 단계',true],['expected','예상 결과',true],['priority','우선순위',false],['tags','태그',false],['group','그룹',false]];
var IMPORT_DEFAULT_MAPPINGS={tc_id:'B열',title:'F열',precondition:'G열',steps:'H열',expected:'I열',priority:'J열'};
var _importStudio={step:1,files:[],file:'',sheets:[],selectedSheets:[],platforms:['android','ios'],mappings:Object.assign({},IMPORT_DEFAULT_MAPPINGS),policy:'skip-conflict',preview:null,previewFilter:'all',previewLoading:false,previewError:'',loading:false,error:'',result:null};
var _importPreviewRequest=0;

function importFormatSize(bytes){
  if(!bytes) return '0 B';
  if(bytes<1024) return bytes+' B';
  return (bytes/1024).toFixed(1)+' KB';
}
function importFormatDate(value){
  if(!value) return '';
  try{return new Date(value).toLocaleDateString('ko-KR');}catch(_){return '';}
}
function importWizardHeader(){
  var labels=['파일 선택','열 매핑','미리보기','안전한 반영','완료'], html='';
  labels.forEach(function(label,index){
    var number=index+1, done=number<_importStudio.step, active=number===_importStudio.step;
    html+='<div class="is-step"><div class="is-step-circle '+(done?'done':active?'active':'')+'">'+(done?'✓':number)+'</div><div class="is-step-label '+(active?'active':'')+'">'+label+'</div></div>';
    if(number<labels.length) html+='<div class="is-step-line '+(done?'done':'')+'"></div>';
  });
  return html;
}
function importBottomBar(options){
  options=options||{};
  return '<div class="is-bottom"><div class="is-safe-note">원본 파일은 변경되지 않습니다</div><div class="is-spacer"></div>'
    +(options.count?'<span class="is-count">'+options.count+'</span>':'')
    +(options.back?'<button class="is-btn" onclick="importStudioPrev()">이전</button>':'')
    +(options.next?'<button class="is-btn '+(options.success?'success':'primary')+'" onclick="'+options.action+'" '+(options.disabled?'disabled':'')+'>'+options.next+'</button>':'')+'</div>';
}
function importEffectivePlatforms(sheetName){
  var normalized=(sheetName||'').trim().toLowerCase();
  if(normalized==='android'||normalized==='ios')return _importStudio.platforms.indexOf(normalized)>=0?[normalized]:[];
  return _importStudio.platforms.slice();
}
function importPreviewStats(){
  var stats={sheetCount:0,sourceRows:0,generatedFiles:0,sheetNames:[],outputPaths:[]};
  _importStudio.sheets.forEach(function(sheet){
    if(_importStudio.selectedSheets.indexOf(sheet.name)<0)return;
    var platforms=importEffectivePlatforms(sheet.name);if(!platforms.length)return;
    stats.sheetCount++;stats.sourceRows+=sheet.count||0;stats.generatedFiles+=(sheet.count||0)*platforms.length;stats.sheetNames.push(sheet.name);
    platforms.forEach(function(platform){
      var normalized=(sheet.name||'').trim().toLowerCase();
      var path='testcases/'+platform+'/'+((normalized===platform)?'':'{시트명}/');
      if(stats.outputPaths.indexOf(path)<0)stats.outputPaths.push(path);
    });
  });
  return stats;
}
function renderImportStudio(){
  var root=document.getElementById('import-studio-root'); if(!root)return;
  var view=document.getElementById('view-import');
  if(view){view.classList.toggle('is-source-expanded',_importStudio.step===1&&!!_importStudio.file);view.classList.toggle('is-stage-detail',_importStudio.step>=2&&_importStudio.step<=4);view.classList.toggle('is-stage-mapping',_importStudio.step===2);view.classList.toggle('is-stage-preview',_importStudio.step===3);view.classList.toggle('is-stage-commit',_importStudio.step===4);view.classList.toggle('is-stage-complete',_importStudio.step===5);}
  var body='';
  if(_importStudio.step===1){
    var cards=_importStudio.files.map(function(file){
      var selected=file.name===_importStudio.file;
      var sheetRows=selected?'<div class="is-file-sheets" onclick="event.stopPropagation()">'+(file.sheets||[]).map(function(sheet){
        var checked=_importStudio.selectedSheets.indexOf(sheet.name)>=0;
        return '<label class="is-sheet-row"><input type="checkbox" '+(checked?'checked':'')+' onchange="toggleImportSheet(decodeURIComponent(\''+encodeURIComponent(sheet.name)+'\'),this.checked)"><span class="is-sheet-name">'+esc(sheet.name)+'</span><span class="is-sheet-count">'+sheet.count+'행</span></label>';
      }).join('')+'</div>':'';
      return '<div role="checkbox" tabindex="0" aria-checked="'+selected+'" class="is-file-card '+(selected?'selected':'')+'" onclick="selectImportSource(decodeURIComponent(\''+encodeURIComponent(file.name)+'\'))" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();this.click()}"><div class="is-file-head"><div class="is-excel-icon">X</div><div class="is-file-info"><div class="is-file-name">'+esc(file.name)+'</div><div class="is-file-meta">'+importFormatSize(file.size)+' · '+importFormatDate(file.modified_at)+' · '+(file.sheets||[]).length+'개 시트</div></div><div class="is-file-check">'+(selected?'✓':'')+'</div></div>'+sheetRows+'</div>';
    }).join('');
    body='<div class="is-content"><p class="is-description">import/ 폴더의 Excel 파일을 선택하고, 가져올 시트와 대상 그룹을 지정하세요.</p><div class="is-file-grid">'+(cards||'<div class="tc-folder-empty">import/ 폴더에 Excel 파일이 없습니다.</div>')+'</div></div>'
      +importBottomBar({count:_importStudio.selectedSheets.length?'1개 파일 · '+_importStudio.selectedSheets.length+'개 시트 선택됨':'0개 파일 선택됨',next:'다음: 열 매핑 →',action:'importStudioNext()',disabled:!_importStudio.file||!_importStudio.selectedSheets.length});
  }else if(_importStudio.step===2){
    var excelColumns=Array.from({length:26},function(_,index){return String.fromCharCode(65+index)+'열';});
    var mapRows=IMPORT_FIELDS.map(function(field){
      var key=field[0],label=field[1],required=field[2],value=_importStudio.mappings[key]||'';
      var options=[''].concat(excelColumns).map(function(column){return '<option value="'+column+'" '+(column===value?'selected':'')+'>'+(column||'— 선택 안 함 —')+'</option>';}).join('');
      return '<div class="is-map-row"><span class="is-drag">⠿</span><select class="is-map-select" data-field="'+key+'" onchange="setImportMapping(this.dataset.field,this.value)">'+options+'</select><span class="is-map-arrow">→</span><span class="is-map-target">'+label+(required?' <b style="color:#f87171">*</b>':'')+'</span><span class="is-map-ok">'+(value?'✓':'')+'</span></div>';
    }).join('');
    var requiredValid=IMPORT_FIELDS.filter(function(field){return field[2];}).every(function(field){return !!_importStudio.mappings[field[0]];});
    var left='<section class="is-subpanel"><div class="is-subpanel-head"><span class="is-subpanel-title">선택한 파일</span><span class="is-panel-badge">1</span></div><div class="is-subpanel-body"><div class="is-mini-file"><span class="is-mini-excel">X</span><span class="is-mini-name">'+esc(_importStudio.file)+'</span><span class="is-mini-ok">✓</span></div><div class="is-mini-meta">'+_importStudio.selectedSheets.map(esc).join(', ')+'</div><div class="is-platforms"><label><input type="checkbox" value="android" '+(_importStudio.platforms.indexOf('android')>=0?'checked':'')+' onchange="toggleImportPlatform(this.value,this.checked)">Android</label><label><input type="checkbox" value="ios" '+(_importStudio.platforms.indexOf('ios')>=0?'checked':'')+' onchange="toggleImportPlatform(this.value,this.checked)">iOS</label></div></div></section>';
    var center='<section class="is-subpanel"><div class="is-subpanel-head"><span class="is-subpanel-title">공통 열 매핑</span><span class="is-panel-badge">'+Object.keys(_importStudio.mappings).length+'</span></div><div class="is-map-header"><span></span><span>소스 필드 (Excel)</span><span></span><span>대상 필드 (QA-Native)</span><span></span></div><div class="is-mapping-list">'+mapRows+'</div><div class="is-map-hint">필수 필드(*)를 모두 연결해야 미리보기를 생성할 수 있습니다.</div></section>';
    var preview=_importStudio.preview||{summary:{},rows:[]},previewSummary=preview.summary||{};
    var validationMessage=_importStudio.previewLoading?'현재 매핑을 검증하고 있습니다.':_importStudio.previewError?esc(_importStudio.previewError):'상세 테스트 케이스는 다음 미리보기 단계에서 확인할 수 있습니다.';
    var right='<section class="is-subpanel"><div class="is-subpanel-head"><span class="is-subpanel-title">검증 결과</span><span class="is-panel-badge">'+((preview.rows||[]).length)+'</span></div><div class="is-subpanel-body"><div class="is-kpi-grid"><div class="is-kpi"><div class="is-kpi-label">추가</div><div class="is-kpi-number added">'+(previewSummary.added||0)+'</div></div><div class="is-kpi"><div class="is-kpi-label">업데이트</div><div class="is-kpi-number updated">'+(previewSummary.updated||0)+'</div></div><div class="is-kpi"><div class="is-kpi-label">충돌</div><div class="is-kpi-number conflict">'+(previewSummary.conflict||0)+'</div></div><div class="is-kpi"><div class="is-kpi-label">오류</div><div class="is-kpi-number error">'+(previewSummary.error||0)+'</div></div><div class="is-kpi wide"><div class="is-kpi-label">동일 · 변경 불필요</div><div class="is-kpi-number same">'+(previewSummary.same||0)+'</div></div></div><div class="is-safe-box" style="padding:13px;font-size:11px;line-height:1.6">'+validationMessage+'</div><div class="is-legend"><span><i style="background:#34d399"></i>추가</span><span><i style="background:#60a5fa"></i>업데이트</span><span><i style="background:#fbbf24"></i>충돌</span><span><i style="background:#f87171"></i>오류</span><span><i style="background:#9b97b4"></i>동일</span></div></div></section>';
    body='<div class="is-content" style="overflow:hidden"><div class="is-step2-layout">'+left+center+right+'</div></div>'+importBottomBar({back:true,next:_importStudio.previewLoading?'검증 중...':'미리보기 생성 →',action:'importStudioNext()',disabled:!requiredValid||!_importStudio.platforms.length||_importStudio.previewLoading||!_importStudio.preview});
  }else if(_importStudio.step===3){
    var fullPreview=_importStudio.preview||{summary:{},rows:[]},fullSummary=fullPreview.summary||{},fullRows=fullPreview.rows||[];
    var fullStatusLabels={added:'추가',updated:'업데이트',conflict:'충돌',error:'오류',same:'동일'};
    var filters=[['all','전체',fullRows.length],['added','추가',fullSummary.added||0],['updated','업데이트',fullSummary.updated||0],['conflict','충돌',fullSummary.conflict||0],['error','오류',fullSummary.error||0],['same','동일',fullSummary.same||0]];
    var filterHtml=filters.map(function(filter){return '<button type="button" class="is-filter-btn '+(_importStudio.previewFilter===filter[0]?'active':'')+'" onclick="setImportPreviewFilter(\''+filter[0]+'\')">'+filter[1]+' '+filter[2]+'</button>';}).join('');
    var visibleRows=fullRows.filter(function(row){return _importStudio.previewFilter==='all'||row.status===_importStudio.previewFilter;});
    var fullTableRows=visibleRows.map(function(row){return '<tr><td>'+esc(row.tc_id||'-')+'</td><td>'+esc(row.title||'-')+'</td><td>'+esc(row.precondition||'-')+'</td><td>'+esc(row.steps||'-')+'</td><td>'+esc(row.expected||'-')+'</td><td>'+esc(row.group||row.sheet||'-')+'</td><td><span class="is-status-pill '+esc(row.status)+'">'+esc(fullStatusLabels[row.status]||row.status)+'</span></td></tr>';}).join('');
    if(!fullTableRows)fullTableRows='<tr><td class="is-empty-row" colspan="7">선택한 상태의 테스트 케이스가 없습니다.</td></tr>';
    body='<div class="is-full-preview"><div class="is-preview-filters">'+filterHtml+'</div><div class="is-full-table-wrap"><table class="is-full-table"><colgroup><col style="width:8%"><col style="width:16%"><col style="width:19%"><col style="width:22%"><col style="width:22%"><col style="width:8%"><col style="width:7%"></colgroup><thead><tr><th>TC ID</th><th>제목</th><th>전제조건</th><th>테스트 단계</th><th>기대결과</th><th>그룹</th><th>상태</th></tr></thead><tbody>'+fullTableRows+'</tbody></table></div></div>'
      +importBottomBar({back:true,next:'안전한 반영 →',action:'importStudioNext()'});
  }else if(_importStudio.step===4){
    var commitStats=importPreviewStats();
    var platformNames=_importStudio.platforms.map(function(platform){return platform==='ios'?'iOS':'Android';}).join(' · ');
    var outputPaths=commitStats.outputPaths.join(', ');
    var policies=[
      {key:'skip-conflict',badge:'권장',tone:'rec',name:'skip-conflict',desc:'새 파일만 생성하고 동일 경로의 기존 파일은 건너뜁니다.'},
      {key:'overwrite',badge:'주의',tone:'warn',name:'overwrite',desc:'동일 경로의 기존 Markdown을 Excel 데이터로 덮어씁니다.'}
    ];
    var policyCards=policies.map(function(policy){return '<button type="button" class="is-policy-card '+(_importStudio.policy===policy.key?'selected':'')+'" onclick="selectImportPolicy(\''+policy.key+'\')"><span class="is-policy-badge '+policy.tone+'">'+policy.badge+'</span><div class="is-policy-name">'+policy.name+'</div><div class="is-policy-desc">'+policy.desc+'</div></button>';}).join('');
    body='<div class="is-content"><p class="is-description">반영 정책을 선택하고 생성 범위를 마지막으로 확인하세요.</p><div class="is-policy-grid">'+policyCards+'</div><div class="is-commit-summary"><h3>반영 요약</h3><div class="is-commit-row"><span class="is-commit-label">대상 플랫폼</span><strong>'+platformNames+'</strong></div><div class="is-commit-row"><span class="is-commit-label">적용 시트</span><strong>'+commitStats.sheetNames.map(esc).join(', ')+'</strong></div><div class="is-commit-row"><span class="is-commit-label">원본 TC</span><strong>'+commitStats.sourceRows+'건</strong></div><div class="is-commit-row"><span class="is-commit-label">예상 생성 파일</span><strong>'+commitStats.generatedFiles+'개</strong></div><div class="is-commit-row"><span class="is-commit-label">저장 경로</span><strong>'+outputPaths+'</strong></div></div><div class="is-snapshot-info"><span>◆</span><span>원본 Excel은 변경하지 않습니다. <b>skip-conflict</b> 선택 시 기존 Markdown도 보존됩니다.</span></div></div>'
      +importBottomBar({back:true,next:_importStudio.loading?'반영 중...':'✓ 반영 시작',action:'commitImportStudio()',disabled:_importStudio.loading,success:true});
  }else{
    var result=_importStudio.result||{};
    body='<div class="is-content"><div class="is-complete"><div class="is-complete-icon">✓</div><h2>Import 완료</h2><p>'+(result.count||0)+'개의 테스트 케이스 Markdown을 생성했습니다.</p><pre>'+esc((result.files||[]).join('\n'))+'</pre></div></div>'
      +importBottomBar({next:'새 Import 시작',action:'resetImportStudio()'});
  }
  root.innerHTML='<div class="is-header"><div class="is-title-row"><div class="is-title">Excel Import Studio</div><button type="button" class="is-reset-btn" onclick="resetImportStudio()" title="Import Studio 입력 초기화">↻ 리셋</button></div><div class="is-wizard">'+importWizardHeader()+'</div></div>'+(_importStudio.error?'<div class="is-error">'+esc(_importStudio.error)+'</div>':'')+'<div class="is-body">'+body+'</div>';
}
async function refreshImportFiles(){
  try{
    var res=await fetch('/api/import/files'), data=await res.json();
    var files=data.files||[];
    _importStudio.files=await Promise.all(files.map(async function(raw){
      var file=typeof raw==='string'?{name:raw,size:0,modified_at:''}:raw;
      try{var sr=await fetch('/api/import/sheets?file='+encodeURIComponent(file.name)), sd=await sr.json();file.sheets=sd.sheets||[];}catch(_){file.sheets=[];}
      return file;
    }));
    _importStudio.error=''; renderImportStudio();
  }catch(err){_importStudio.error='Excel 파일을 불러오지 못했습니다.';renderImportStudio();}
}
function selectImportSource(name){
  var file=_importStudio.files.find(function(item){return item.name===name;}); if(!file)return;
  if(_importStudio.file===name){_importStudio.file='';_importStudio.sheets=[];_importStudio.selectedSheets=[];}
  else{_importStudio.file=name;_importStudio.sheets=file.sheets||[];_importStudio.selectedSheets=[];}
  renderImportStudio();
}
function toggleImportSheet(sheet,checked){
  _importStudio.selectedSheets=_importStudio.selectedSheets.filter(function(item){return item!==sheet;});
  if(checked)_importStudio.selectedSheets.push(sheet);
  renderImportStudio();
}
function toggleImportPlatform(platform,checked){
  _importStudio.platforms=_importStudio.platforms.filter(function(item){return item!==platform;});
  if(checked)_importStudio.platforms.push(platform);
  renderImportStudio();loadImportPreview();
}
function setImportMapping(field,column){
  if(column)_importStudio.mappings[field]=column;else delete _importStudio.mappings[field];
  renderImportStudio();loadImportPreview();
}
function selectImportPolicy(policy){
  if(policy!=='skip-conflict'&&policy!=='overwrite')return;
  _importStudio.policy=policy;renderImportStudio();
}
function setImportPreviewFilter(filter){_importStudio.previewFilter=filter;renderImportStudio();}
function importStudioNext(){if(_importStudio.step===2&&(!_importStudio.preview||_importStudio.previewLoading))return;if(_importStudio.step<4){_importStudio.step++;_importStudio.error='';renderImportStudio();if(_importStudio.step===2)loadImportPreview();}}
function importStudioPrev(){if(_importStudio.step>1){_importStudio.step--;_importStudio.error='';renderImportStudio();}}
function resetImportStudio(){_importPreviewRequest++;_importStudio={step:1,files:_importStudio.files,file:'',sheets:[],selectedSheets:[],platforms:['android','ios'],mappings:Object.assign({},IMPORT_DEFAULT_MAPPINGS),policy:'skip-conflict',preview:null,previewFilter:'all',previewLoading:false,previewError:'',loading:false,error:'',result:null};renderImportStudio();}
async function loadImportPreview(){
  if(_importStudio.step!==2||!_importStudio.file||!_importStudio.selectedSheets.length||!_importStudio.platforms.length)return;
  var request=++_importPreviewRequest;_importStudio.previewLoading=true;_importStudio.previewError='';renderImportStudio();
  try{
    var res=await fetch('/api/import/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:_importStudio.file,sheets:_importStudio.selectedSheets,platforms:_importStudio.platforms,mappings:_importStudio.mappings})});
    var data=await res.json();if(!data.ok)throw new Error(data.error||'미리보기 실패');
    if(request===_importPreviewRequest)_importStudio.preview=data;
  }catch(err){if(request===_importPreviewRequest){_importStudio.preview=null;_importStudio.previewError=err.message||'미리보기에 실패했습니다.';}}
  finally{if(request===_importPreviewRequest){_importStudio.previewLoading=false;renderImportStudio();}}
}
async function commitImportStudio(){
  _importStudio.loading=true;_importStudio.error='';renderImportStudio();
  try{
    var combined={count:0,files:[]};
    for(var index=0;index<_importStudio.selectedSheets.length;index++){
      var sheet=_importStudio.selectedSheets[index];
      var res=await fetch('/api/import/convert',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:_importStudio.file,sheet:sheet,platforms:_importStudio.platforms,mappings:_importStudio.mappings,policy:_importStudio.policy})});
      var data=await res.json();if(!data.ok)throw new Error(data.error||sheet+' 변환 실패');
      combined.count+=data.count||0;combined.files=combined.files.concat(data.files||[]);
    }
    _importStudio.result=combined;_importStudio.step=5;refreshTcFolders();
  }catch(err){_importStudio.error=err.message||'변환에 실패했습니다.';}finally{_importStudio.loading=false;renderImportStudio();}
}
