// ── 상태 ────────────────────────────────────────────────────
var _pollTimer = null;
var _currentLog = 'run_execute.txt';
var _currentStep = null;
var _initialPlatformSync = true;  // Fix 4: 최초 로드 시 한 번만 플랫폼 동기화
var _logExpanded = false;
var _stepStartTime = null;
function _analyzeFailMsg(){
  return getPlatform() === 'ios'
    ? 'Appium 연결 또는 iOS Simulator 상태를 확인하세요. (xcrun simctl list devices booted) 재실행 권장.'
    : 'Appium 연결 또는 Android 디바이스 상태를 확인하세요. (adb devices) 재실행 권장.';
}
var _guideMessages = {
  analyze:  {ok:"다음: 코드 생성 (2단계)을 실행하세요.",  fail:null},
  generate: {ok:"다음: 린트 검사 (3단계)를 실행하세요.",  fail:"TC 마크다운 또는 screens.json 설정을 확인하세요."},
  lint:     {ok:"다음: 테스트 실행 (4단계)을 실행하세요.", fail:"생성된 코드에 문법 오류. 수정 후 lint 재실행 or heal 실행."},
  execute:  {ok:"다음: 완료. 리포트를 확인하세요.",        fail:"테스트 실패 발생. 아래 실패 목록 확인. heal 실행으로 자동 패치 시도 가능."},
  heal:     {ok:"파이프라인 완료! 리포트를 확인하세요.",   fail:"자동 패치 실패. 수동 수정 필요."}
};
var _nextStep = {
  analyze:'generate', generate:'lint', lint:'execute', execute:null, heal:null
};
// 소프트 순서 강제: 이 단계가 done이어야 다음 단계가 활성화
var _prereq = {
  analyze: null, generate:'analyze', lint:'generate', execute:'lint', heal:'execute'
};
var STEP_ORDER = ['analyze','generate','lint','execute','heal'];
var STEP_LABEL = {analyze:'분석',generate:'생성',lint:'린트',execute:'실행',heal:'힐링'};
var _stepState = {analyze:'idle',generate:'idle',lint:'idle',execute:'idle',heal:'idle'};
var _overviewLogMode='pipeline';

function getPlatform(){
  return document.querySelector('input[name="platform"]:checked').value;
}

function getTcFolders(){
  return Array.from(document.querySelectorAll('input[name="tc-folder"]:checked')).map(function(el){ return el.value; });
}
function getTcFolder(){
  return getTcFolders()[0] || '';
}
function setOverviewLog(mode){
  if(mode!=='pipeline'&&mode!=='quick')return;
  _overviewLogMode=mode;
  document.querySelectorAll('.overview-log-tab').forEach(function(button){button.classList.toggle('active',button.dataset.overviewLog===mode);});
  refreshOverview();
}
function renderOverviewTrend(fallbackRate){
  var allEntries=loadRunHistory().slice(0,8).reverse();
  if(!allEntries.length && fallbackRate>0) allEntries=[{rate:fallbackRate,executedAt:new Date().toISOString()}];
  if(!allEntries.length) return '<div class="overview-trend-empty-message">실행 이력 없음</div>';
  var w=320,h=130,padX=28,padY=18,padBot=18;
  var chartH=h-padY-padBot;
  var stepX=allEntries.length>1?(w-padX*2)/(allEntries.length-1):0;
  var pointStr='', areaStr=padX+','+(padY+chartH)+' ', dots='', pctLabels='', tsLabels='';
  var prevLabelY=-100, minGap=12;
  var showEveryN=allEntries.length>5?2:1;
  allEntries.forEach(function(entry,i){
    var rate=Math.max(0,Math.min(100,Number(entry.rate||0)));
    var x=padX+stepX*i;
    var y=padY+chartH-(rate/100)*chartH;
    var color=rate>=100?'var(--pass)':rate>=80?'var(--warn)':'var(--fail)';
    pointStr+=x+','+y+' ';
    areaStr+=x+','+y+' ';
    var ts=entry.executedAt?new Date(entry.executedAt).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false}):'';
    dots+='<circle cx="'+x+'" cy="'+y+'" r="3.5" fill="'+color+'" stroke="rgba(8,7,27,0.6)" stroke-width="1.5" style="filter:drop-shadow(0 0 3px '+color+')"/>';
    var labelY=y-8;
    if(Math.abs(labelY-prevLabelY)<minGap){
      labelY=prevLabelY<y?y+14:y-8-minGap+Math.abs(labelY-prevLabelY);
    }
    pctLabels+='<text x="'+x+'" y="'+labelY+'" text-anchor="middle" fill="'+color+'" font-size="9" font-weight="600" font-family="Inter">'+rate+'%</text>';
    prevLabelY=labelY;
    if(i===0||i===allEntries.length-1||i%showEveryN===0){
      tsLabels+='<text x="'+x+'" y="'+(h-3)+'" text-anchor="middle" fill="var(--text3)" font-size="9" font-family="Inter">'+ts+'</text>';
    }
  });
  areaStr+=padX+stepX*(allEntries.length-1)+','+(padY+chartH);
  var gridLines=[100,80,60].map(function(v){
    var gy=padY+chartH-(v/100)*chartH;
    return '<line x1="'+padX+'" y1="'+gy+'" x2="'+(w-padX)+'" y2="'+gy+'" stroke="rgba(140,120,220,0.06)" stroke-width="0.5"/>';
  }).join('');
  return '<svg viewBox="0 0 '+w+' '+h+'" class="overview-trend-svg"><defs><linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--accent)" stop-opacity="0.2"/><stop offset="100%" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>'+gridLines+'<polygon points="'+areaStr+'" fill="url(#areaGrad)"/><polyline points="'+pointStr+'" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="filter:drop-shadow(0 0 4px var(--accent))"/>'+dots+pctLabels+tsLabels+'</svg>';
}
async function refreshOverview(){
  try{
    var pipelineLogRequest=_overviewLogMode==='pipeline'
      ? fetch('/api/run_log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({log:_currentLog||'run_execute.txt'})}).then(function(r){return r.json();}).catch(function(){return {}; })
      : Promise.resolve({});
    var results=await Promise.all([
      fetch('/api/state').then(function(r){return r.json();}).catch(function(){return {}; }),
      fetch('/api/status').then(function(r){return r.json();}).catch(function(){return {}; }),
      fetch('/api/generated').then(function(r){return r.json();}).catch(function(){return []; }),
      pipelineLogRequest
    ]);
    var state=results[0]||{}, status=results[1]||{}, generated=results[2]||[], log=results[3]||{};
    var summary=(state.execute_results||{}).summary||{};
    var total=summary.total||0, passed=summary.passed||0, failed=summary.failed||0;
    var quickSummary=null;
    var quickActive=null;
    try{
      ['android','ios'].forEach(function(platform){
        var raw=localStorage.getItem('qa-native-app.quick-summary.'+platform); if(!raw)return;
        var item=JSON.parse(raw); if(item && (!quickSummary || (item.executedAt||'')>(quickSummary.executedAt||'')))quickSummary=item;
      });
      ['android','ios'].forEach(function(platform){
        var raw=localStorage.getItem('qa-native-app.quick-active.'+platform); if(!raw)return;
        var item=JSON.parse(raw); if(item)quickActive=item;
      });
    }catch(_){ }
    if(quickActive){
      quickSummary={platform:quickActive.platform,total:quickActive.total||0,passed:quickActive.passed||0,failed:quickActive.failed||0,rate:quickActive.total?Math.round((quickActive.passed||0)/quickActive.total*100):0,executedAt:quickActive.startedAt||''};
      _overviewLogMode='quick';
      document.querySelectorAll('.overview-log-tab').forEach(function(button){button.classList.toggle('active',button.dataset.overviewLog==='quick');});
    }
    if(quickSummary){ total=quickSummary.total||0; passed=quickSummary.passed||0; failed=quickSummary.failed||0; }
    var rate=total?Math.round(passed/total*100):0;
    var trendColor=rate>=100?'var(--pass)':rate>=80?'var(--warn)':'var(--fail)';
    var trendY=120-(rate*.92);
    var set=function(id,value){var el=document.getElementById(id);if(el)el.textContent=value;};
    set('overview-rate',rate);
    set('overview-total',total);
    set('overview-passed',passed);
    set('overview-failed',failed);
    set('overview-appium',status.appium?'연결됨':'미기동');
    set('overview-healing',(state.heal_count||0)+'회');
    set('overview-generated',generated.reduce(function(n,g){return n+(g.count||0);},0)+'개');
    set('overview-quick',quickSummary ? quickSummary.passed+'/'+quickSummary.total+' · '+quickSummary.rate+'%' : '실행 없음');
    var donut=document.getElementById('overview-donut-fill');
    if(donut) donut.setAttribute('stroke-dasharray',(302*rate/100)+' 302');
    var ctxTimeStr=quickSummary&&quickSummary.executedAt?new Date(quickSummary.executedAt).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}):'';
    set('overview-context',quickSummary && (!summary.total || (quickSummary.executedAt||'')>(state.updated_at||'')) ? '빠른 실행 · '+ctxTimeStr : (total?'최근 '+(state.platform==='ios'?'iOS':'Android')+' 실행':'최근 실행 없음'));
    var overviewLog='';
    if(_overviewLogMode==='pipeline'){
      overviewLog=log.log||'';
    }else{
      try{
        var quickPlatform=quickSummary&&quickSummary.platform?quickSummary.platform:'android';
        overviewLog=localStorage.getItem((quickActive?'qa-native-app.quick-live-log.':'qa-native-app.quick-log.')+quickPlatform)||'';
      }catch(_){overviewLog='';}
    }
    set('overview-log',overviewLog||'로그 없음');
    var trend=document.getElementById('overview-trend');
    if(trend){
      var trendEntries=loadRunHistory();
      trend.className=(trendEntries.length||total)?'overview-trend-chart':'overview-trend-empty';
      var lastEntry=trendEntries.length?trendEntries[0]:null;
      var footerLeft=lastEntry?(lastEntry.duration?lastEntry.duration+' · ':'')+(lastEntry.failed?'Failed':'First Pass'):'실행 추이';
      trend.innerHTML=renderOverviewTrend(rate)
        +'<div class="overview-trend-footer"><span>'+footerLeft+'</span><span class="overview-trend-legend"><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--pass)"></i>100%</span><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--warn)"></i>80%↑</span><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--fail)"></i>80%↓</span></span></div>';
    }
  }catch(_){
    // Dashboard remains usable when an optional status/log endpoint is unavailable.
  }
}
function toggleAllTcFolders(checked){
  document.querySelectorAll('input[name="tc-folder"]').forEach(function(el){ el.checked=checked; });
  updateTcFolderCount();
}
function updateTcFolderCount(){
  var selected=getTcFolders(), el=document.getElementById('tc-folder-count');
  if(el) el.textContent=selected.length ? selected.length+'개 폴더를 선택한 순서대로 직렬 실행합니다.' : '실행할 폴더를 선택하세요.';
}

function selectView(view, item){
  document.querySelectorAll('.sidebar-item').forEach(function(el){
    el.classList.toggle('active', el === item);
  });
  var grid=document.querySelector('.grid');
  var pipeline=document.getElementById('view-pipeline');
  var overview=document.getElementById('view-overview');
  var rightViews=['tests','import','reports','history','config','capture'];
  if(!grid || !pipeline) return;
  if(overview) overview.classList.toggle('view-hidden', view !== 'dashboard');
  grid.classList.toggle('view-hidden', view === 'dashboard');
  grid.classList.remove('focus-left','focus-right');
  pipeline.classList.remove('view-hidden');
  document.querySelectorAll('.right-panel > .card').forEach(function(card){
    card.classList.toggle('view-hidden', view !== 'dashboard' && card.id !== 'view-'+view);
  });
  if(view === 'pipeline') grid.classList.add('focus-left');
  if(rightViews.indexOf(view) !== -1) grid.classList.add('focus-right');
  var main = document.querySelector('.app-main');
  if(main) main.classList.toggle('dashboard-view', view === 'dashboard');
  document.body.classList.toggle('quick-mode', view === 'tests');
  document.body.classList.toggle('report-mode', view === 'reports');
  document.body.classList.toggle('dashboard-mode', view === 'dashboard');
  if(main) main.classList.toggle('report-view', view === 'reports');
  if(main) main.classList.toggle('import-view', view === 'import');
  if(main) main.classList.toggle('capture-view', view === 'capture');
  if(main) main.classList.toggle('quick-view', view === 'tests');
  if(main) main.classList.toggle('history-view', view === 'history');
  if(view === 'dashboard') refreshOverview();
  if(view === 'tests') refreshStatus();
  if(main) main.scrollTo({top:0, behavior:'smooth'});
}

function loadRunHistory(){
  try{return JSON.parse(localStorage.getItem('qa-native-app.run-history')||'[]');}catch(_){return [];}
}
function renderRunHistory(){
  var entries=loadRunHistory(), list=document.getElementById('history-list');
  if(!list||!entries.length)return;
  list.innerHTML=entries.map(function(entry){
    var date=new Date(entry.executedAt||Date.now()), dateText=date.toLocaleDateString('ko-KR').replace(/\. /g,'-').replace(/\.$/,'');
    var time=date.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
    var groups=(entry.groups||[]).map(function(group){return '<span class="history-group">'+esc(group)+'</span>';}).join('');
    var ok=!entry.failed;
    return '<div class="history-row" data-history-type="'+esc(entry.type||'quick')+'" data-history-platform="'+esc(entry.platform||'android')+'" data-history-groups="'+esc((entry.groups||[]).join(' '))+'">'
      +'<div class="history-date"><strong>'+esc(dateText)+'<br>'+esc(time)+'</strong></div>'
      +'<div><div class="history-pass" style="color:'+(ok?'var(--pass)':'var(--fail)')+'">'+entry.rate+'%</div><div class="history-progress"><span style="width:'+entry.rate+'%;background:'+(ok?'var(--pass)':'var(--fail)')+'"></span></div></div>'
      +'<div><span class="history-count">'+entry.passed+'<small> / '+entry.total+'</small></span><div style="color:var(--text3);font-size:11px;margin-top:3px">'+(entry.duration||'-')+'</div></div>'
      +'<div><span class="history-type">'+(entry.type==='pipeline'?'파이프라인 실행':'빠른 실행')+'</span></div><div><span class="history-platform '+esc(entry.platform||'android')+'">'+(entry.platform==='ios'?'🍎 iOS':'🤖 Android')+'</span></div>'
      +'<div class="history-groups">'+groups+'</div><div><span class="history-result" style="color:'+(ok?'var(--pass)':'var(--fail)')+';border-color:'+(ok?'rgba(52,211,153,.3)':'rgba(251,113,133,.3)')+'">'+(ok?'First Pass':'Failed')+'</span></div></div>';
  }).join('');
  var total=entries.length, passedRate=Math.round(entries.reduce(function(sum,item){return sum+(item.rate||0);},0)/total);
  var passedFirst=entries.filter(function(item){return !item.failed&&item.rate===100;}).length;
  document.getElementById('history-total').textContent=total;
  document.getElementById('history-rate').textContent=passedRate+'%';
  document.getElementById('history-first').innerHTML=passedFirst+'<span class="history-kpi-suffix">/'+total+'</span>';
  document.getElementById('history-heal').textContent=entries.reduce(function(sum,item){return sum+(item.healCount||0);},0);
}
function recordRunHistory(entry){
  var entries=loadRunHistory(); entries.unshift(entry); entries=entries.slice(0,50);
  try{localStorage.setItem('qa-native-app.run-history',JSON.stringify(entries));}catch(_){ }
  renderRunHistory();
}

function resetHistory(){
  if(!window.confirm('실행 히스토리를 초기화할까요?')) return;
  document.getElementById('history-total').textContent='0';
  document.getElementById('history-rate').textContent='0%';
  document.getElementById('history-first').innerHTML='0<span class="history-kpi-suffix">/0</span>';
  document.getElementById('history-heal').textContent='0';
  document.getElementById('history-list').innerHTML='<div class="history-empty">실행 이력이 없습니다.</div>';
  try{localStorage.removeItem('qa-native-app.run-history');}catch(_){ }
  document.querySelectorAll('.history-filter').forEach(function(btn){btn.classList.toggle('active',btn.dataset.filterValue==='all');});
}

document.addEventListener('click', function(e){
  if(e.target && e.target.classList.contains('history-filter')){
    var kind=e.target.dataset.filterKind;
    var selector=kind==='platform' ? '.history-filter.platform-filter' : kind==='group' ? '.history-filter.group' : '.history-filter:not(.group):not(.platform-filter)';
    e.target.parentElement.querySelectorAll(selector).forEach(function(btn){btn.classList.remove('active');});
    e.target.classList.add('active');
    document.querySelectorAll('.history-row:not(.header)').forEach(function(row){
      var typeBtn=document.querySelector('.history-filter[data-filter-kind="type"].active');
      var groupBtn=document.querySelector('.history-filter[data-filter-kind="group"].active');
      var platformBtn=document.querySelector('.history-filter[data-filter-kind="platform"].active');
      var groups=(row.dataset.historyGroups||'').split(' ');
      var visible=(!typeBtn||typeBtn.dataset.filterValue==='all'||row.dataset.historyType===typeBtn.dataset.filterValue)
        &&(!groupBtn||groupBtn.dataset.filterValue==='all'||groups.indexOf(groupBtn.dataset.filterValue)!==-1)
        &&(!platformBtn||platformBtn.dataset.filterValue==='all'||row.dataset.historyPlatform===platformBtn.dataset.filterValue);
      row.style.display=visible?'':'none';
    });
  }
});

function updateStepLocks(){
  STEP_ORDER.forEach(function(step){
    var btn = document.getElementById('btn-'+step);
    if(!btn || btn.classList.contains('loading')) return;
    var pre = _prereq[step];
    var locked = pre && _stepState[pre] !== 'done';
    btn.disabled = locked;
    btn.title = locked ? ('이전 단계(' + STEP_LABEL[pre] + ')를 먼저 완료하세요') : '';
    btn.style.opacity = locked ? '0.45' : '';
  });
}

function toggleLog(){
  _logExpanded = !_logExpanded;
  var box = document.getElementById('log-box');
  box.style.maxHeight = _logExpanded ? '500px' : '180px';
  document.getElementById('log-toggle').textContent = _logExpanded ? '축소' : '확장';
}

function renderProgressBar(){
  var bar = document.getElementById('progress-bar');
  if(!bar) return;
  var doneCount = STEP_ORDER.filter(function(s){ return _stepState[s]==='done'; }).length;
  var html = '';
  STEP_ORDER.forEach(function(s, i){
    var st = _stepState[s];
    var color = {done:'#10b981',failed:'#f43f5e',running:'#6366f1',idle:'rgba(255,255,255,.15)',skipped:'rgba(255,255,255,.08)'}[st]||'rgba(255,255,255,.15)';
    var border = st==='skipped' ? '1px dashed rgba(255,255,255,.2)' : 'none';
    var anim = st==='running' ? 'animation:pulse 1s infinite' : '';
    html += '<div style="display:flex;flex-direction:column;align-items:center;flex:1;gap:3px">'
      + '<div style="width:16px;height:16px;border-radius:50%;background:'+color+';border:'+border+';'+anim+';flex-shrink:0"></div>'
      + '<span style="font-size:11px;color:rgba(255,255,255,.45)">'+STEP_LABEL[s]+'</span>'
      + '</div>';
    if(i < STEP_ORDER.length - 1){
      var lineColor = (_stepState[STEP_ORDER[i]]==='done') ? '#10b981' : 'rgba(255,255,255,.1)';
      html += '<div style="flex:1;height:2px;background:'+lineColor+';margin-bottom:14px;margin-top:7px"></div>';
    }
  });
  html += '<span style="font-size:12px;color:#8c87a8;margin-left:8px;white-space:nowrap">'+doneCount+'/5</span>';
  bar.innerHTML = html;
}

function setStepState(step, state){
  if(_stepState[step] !== undefined) _stepState[step] = state;
  renderProgressBar();
  updateStepLocks();
}

function setLog(text){
  var b=document.getElementById('log-box');
  b.textContent=text;
  b.scrollTop=b.scrollHeight;
}
function clearLog(){
  document.getElementById('log-box').textContent='';
  hideFails();
}

async function resetDashboard(){
  if(!window.confirm('실행 중인 파이프라인을 중지하고 상태를 초기화할까요?')) return;
  var btn=document.getElementById('reset-btn');
  if(btn){ btn.disabled=true; btn.textContent='초기화 중...'; }
  try{
    var res=await fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    var data=await res.json();
    if(!data.ok) throw new Error(data.error||'초기화 실패');
    if(_pollTimer){ clearInterval(_pollTimer); _pollTimer=null; }
    _currentStep=null; _runAllActive=false;
    STEP_ORDER.forEach(function(step){ _stepState[step]='idle'; setStepNum(step,''); });
    hideFails(); closeReport(); clearLog(); renderProgressBar(); updateStepLocks();
    var healRow=document.getElementById('heal-row');
    var healCount=document.getElementById('heal-cnt');
    if(healRow) healRow.style.display='none';
    if(healCount) healCount.textContent='';
    await Promise.all([refreshStatus(),refreshGenerated(),refreshReports(),refreshTcFolders()]);
    setLog('대시보드 상태가 초기화되었습니다.\n새 실행을 시작할 수 있습니다.');
  }catch(err){
    setLog('초기화 실패: '+err.message);
  }finally{
    if(btn){ btn.disabled=false; btn.textContent='↺ 리셋'; }
  }
}

async function resetOverviewDashboard(){
  if(!window.confirm('대시보드의 실행 요약, 로그와 누적 히스토리를 초기화할까요?\n생성 테스트와 리포트 파일은 유지됩니다.')) return;
  var btn=document.getElementById('overview-reset-btn');
  if(btn){btn.disabled=true;btn.textContent='초기화 중...';}
  try{
    var res=await fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    var data=await res.json();
    if(!data.ok) throw new Error(data.error||'초기화 실패');
    if(_pollTimer){clearInterval(_pollTimer);_pollTimer=null;}
    _currentStep=null;_runAllActive=false;
    try{
      localStorage.removeItem('qa-native-app.run-history');
      ['android','ios'].forEach(function(platform){
        localStorage.removeItem('qa-native-app.quick-summary.'+platform);
        localStorage.removeItem('qa-native-app.quick-log.'+platform);
        localStorage.removeItem('qa-native-app.quick-active.'+platform);
        localStorage.removeItem('qa-native-app.quick-live-log.'+platform);
      });
    }catch(_){ }
    var historyList=document.getElementById('history-list');
    if(historyList) historyList.innerHTML='<div class="history-empty">실행 이력이 없습니다.</div>';
    var historyTotal=document.getElementById('history-total');if(historyTotal)historyTotal.textContent='0';
    var historyRate=document.getElementById('history-rate');if(historyRate)historyRate.textContent='0%';
    var historyFirst=document.getElementById('history-first');if(historyFirst)historyFirst.innerHTML='0<span class="history-kpi-suffix">/0</span>';
    var historyHeal=document.getElementById('history-heal');if(historyHeal)historyHeal.textContent='0';
    await refreshOverview();
  }catch(err){
    window.alert('대시보드 초기화 실패: '+err.message);
  }finally{
    if(btn){btn.disabled=false;btn.textContent='↻ 대시보드 초기화';}
  }
}
