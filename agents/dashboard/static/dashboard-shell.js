// In-page confirmation preserves cancellation and keyboard focus.
function dashboardConfirm(message){
  return new Promise(function(resolve){
    var trigger=document.activeElement;
    var dialog=document.createElement('dialog');
    dialog.className='ui-confirm'+(/삭제|종료|중지|초기화/.test(message)?' is-destructive':'');dialog.setAttribute('role','alertdialog');
    dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-labelledby','dashboard-confirm-title');
    dialog.innerHTML='<h2 id="dashboard-confirm-title">작업 확인</h2><p></p><div class="ui-confirm-actions"><button type="button" data-confirm="cancel">취소</button><button type="button" class="confirm-accept" data-confirm="accept">확인</button></div>';
    dialog.querySelector('p').textContent=message;
    function finish(value){dialog.close();dialog.remove();if(trigger&&trigger.isConnected)trigger.focus();resolve(value);}
    dialog.querySelector('[data-confirm="cancel"]').onclick=function(){finish(false);};
    dialog.querySelector('[data-confirm="accept"]').onclick=function(){finish(true);};
    dialog.addEventListener('cancel',function(event){event.preventDefault();finish(false);});
    document.body.appendChild(dialog);dialog.showModal();dialog.querySelector('[data-confirm="cancel"]').focus();
  });
}

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
// 코드 생성은 Markdown만 필요하다. 분석은 기기 UI 수집을 별도로 실행할 때 사용한다.
var _prereq = {
  analyze: null, generate:null, lint:'generate', execute:'lint', heal:'execute'
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
// Overview filters affect presentation only; execution platform and saved state are untouched.
var _overviewPlatform='all';
var _overviewData=null;
function setOverviewPlatform(platform){
  if(['all','android','ios'].indexOf(platform)<0)return;
  _overviewPlatform=platform;
  document.querySelectorAll('.overview-platform-filter button').forEach(function(button,index){button.setAttribute('aria-pressed',['all','android','ios'][index]===platform?'true':'false');});
  if(_overviewData)renderOverviewData(_overviewData);
}
function overviewEntries(){
  return loadRunHistory().filter(function(entry){return _overviewPlatform==='all'||entry.platform===_overviewPlatform;}).slice(0,10);
}
function overviewResult(entry){
  if(!entry)return {text:'—',kind:''};
  if(entry.status==='running')return {text:'실행 중',kind:'warn'};
  if(['cancelled','canceled','stopped','aborted'].indexOf(entry.status)>=0)return {text:'중단',kind:'warn'};
  if(Number(entry.failed)>0||entry.status==='failed')return {text:'실패',kind:'fail'};
  if(Number(entry.total)>0 && Number(entry.passed)===Number(entry.total))return {text:'통과',kind:'pass'};
  return {text:'정보 없음',kind:''};
}
function overviewTime(value){
  var date=new Date(value);
  return value&&!isNaN(date.getTime())?date.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'시간 정보 없음';
}
function overviewDuration(value){
  return value&&value!=='-'?String(value).replace(/^(\d+)s$/,'$1초'):'—';
}
function renderOverviewTrend(){
  var allEntries=overviewEntries().slice(0,8);
  if(!allEntries.length) return '<div class="overview-empty"><strong>실행 이력이 없습니다</strong><p>테스트를 실행하면 결과가 여기에 표시됩니다.</p><button class="btn" onclick="selectView(\'pipeline\',document.querySelector(\'[data-view=pipeline]\'))">파이프라인 열기</button></div>';
  return '<table class="overview-history-table"><thead><tr><th>시작</th><th>종류</th><th>대상</th><th>결과</th><th>통과</th><th>소요</th></tr></thead><tbody>'+allEntries.map(function(entry){
    var result=overviewResult(entry);
    return '<tr data-platform="'+esc(entry.platform||'')+'"><td>'+esc(entry.executedAt?overviewTime(entry.executedAt):'—')+'</td><td>'+esc(entry.type==='quick'?'빠른 실행':entry.type==='pipeline'?'파이프라인':'—')+'</td><td>'+esc(Array.isArray(entry.groups)&&entry.groups.length?entry.groups.join(' · '):'—')+'</td><td><span class="result-badge '+result.kind+'">'+result.text+'</span></td><td>'+esc(Number.isFinite(Number(entry.passed))&&Number.isFinite(Number(entry.total))?entry.passed+'/'+entry.total:'—')+'</td><td>'+esc(overviewDuration(entry.duration))+'</td></tr>';
  }).join('')+'</tbody></table>';
}
function renderOverviewRateChart(entries){
  var points=entries.slice().reverse().filter(function(entry){return Number(entry.total)>0;}).map(function(entry,index,all){
    var rate=Math.max(0,Math.min(100,Math.round(Number(entry.passed||0)/Number(entry.total)*100)));
    var time=entry.executedAt?new Date(entry.executedAt):null;
    return {entry:entry,rate:rate,x:all.length===1?40:40+index*400/(all.length-1),y:32+(100-rate)*.8,label:time&&!isNaN(time.getTime())?time.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false}):'시간 정보 없음',kind:rate===100?'pass':rate>=80?'warn':'fail'};
  });
  if(!points.length)return '<div class="overview-chart-empty">실행 이력이 쌓이면 통과율 추이가 표시됩니다.</div>';
  var description=points.map(function(point){return point.label+' '+point.rate+'%';}).join(', ');
  var grid=[32,59,86].map(function(y){return '<line x1="40" y1="'+y+'" x2="440" y2="'+y+'" class="overview-chart-grid"/>';}).join('');
  var line=points.length>1?'<polyline class="overview-chart-line" points="'+points.map(function(point){return point.x+','+point.y;}).join(' ')+'"/>':'';
  return '<svg class="overview-rate-svg" viewBox="0 0 480 190" role="img" aria-label="통과율 추이: '+esc(description)+'"><title>'+esc(description)+'</title>'+grid+line+points.map(function(point){return '<g class="overview-chart-point '+point.kind+'"><title>'+esc(point.label+' · '+point.rate+'% · '+(point.kind==='pass'?'통과':point.kind==='warn'?'주의':'실패'))+'</title><text x="'+point.x+'" y="'+(point.y-11)+'" text-anchor="middle">'+point.rate+'%</text><circle cx="'+point.x+'" cy="'+point.y+'" r="4"/><text class="overview-chart-time" x="'+point.x+'" y="183" text-anchor="middle">'+esc(point.label)+'</text></g>';}).join('')+'</svg>';
}
function renderOverviewEnvironment(env){
  if(!env)return;
  function put(id,text,connected){var el=document.getElementById(id);if(el){el.textContent=text;el.dataset.connected=String(!!connected);}}
  var appium=env.appium||{},android=env.android||{},ios=env.ios||{};
  var connected=appium.status==='managed'||appium.status==='external';
  var names={managed:'연결됨',external:'연결됨',starting:'시작 중',stopped:'미기동',error:'오류'};
  put('overview-appium',(names[appium.status]||'확인 전')+(appium.port?' · 127.0.0.1:'+appium.port:''),connected);
  var avd=(android.emulators||[]).find(function(device){return device.avd===android.avd;});
  put('overview-android-emulator',android.status==='running'?(android.serial||android.avd||(avd&&avd.deviceName)||'실행 중'):android.status==='starting'?'시작 중':android.status==='error'?'오류':'중지됨',android.status==='running');
  var real=android.real_devices||[];
  put('overview-android-real',real.length?real.map(function(device){return (device.deviceName||device.serial||device.udid||'이름 없음')+(device.connected?'':' · 미연결');}).join(', '):'등록된 실기기 없음',real.some(function(device){return device.connected;}));
  put('overview-ios',ios.status==='running'?(ios.simulator||ios.udid||'실행 중'):ios.status==='starting'?'시작 중':ios.status==='error'?'오류':'중지됨',ios.status==='running');
}
function renderOverviewData(data){
  var state=data.state,status=data.status,generated=data.generated;
  var entries=overviewEntries(),latest=entries[0]||null;
  var candidates=entries.slice(0,1);
  var summary=(state.execute_results||{}).summary;
  if(summary&&Number(summary.total)>0){
    candidates.push(Object.assign({},summary,{platform:state.platform||status.platform,executedAt:state.updated_at||'',duration:summary.duration}));
  }
  if(data.quickSummary)candidates.push(data.quickSummary);
  candidates=candidates.filter(function(entry){return _overviewPlatform==='all'||entry.platform===_overviewPlatform;});
  candidates.sort(function(a,b){return String(b.executedAt||'').localeCompare(String(a.executedAt||''));});
  latest=candidates[0]||null;
  var set=function(id,value){var el=document.getElementById(id);if(el)el.textContent=value;};
  var result=overviewResult(latest);
  set('overview-last-result',result.text);
  var resultEl=document.getElementById('overview-last-result');if(resultEl)resultEl.className=result.kind;
  set('overview-last-detail',latest?(latest.total||0)+'건 중 '+(latest.passed||0)+'건 통과 · 실패 '+(latest.failed||0)+' · 건너뜀 '+(latest.skipped||0)+' · '+overviewDuration(latest.duration):'실행 정보 없음');
  set('overview-context',latest?'마지막 실행 '+overviewTime(latest.executedAt)+' · '+(latest.platform==='ios'?'iOS':latest.platform==='android'?'Android':'플랫폼 정보 없음'):'최근 실행 없음');
  var pass=entries.reduce(function(sum,entry){return sum+(Number(entry.passed)||0);},0);
  var runTotal=entries.reduce(function(sum,entry){return sum+(Number(entry.total)||0);},0);
  set('overview-history-rate',runTotal?Math.round(pass/runTotal*100)+'%':'—');
  set('overview-history-count',entries.length?'통과 '+pass+' · 전체 '+runTotal:'실행 이력 없음');
  var groups=generated.filter(function(group){return _overviewPlatform==='all'||group.platform===_overviewPlatform;});
  set('overview-generated',groups.reduce(function(sum,group){return sum+(Number(group.count)||0);},0));
  set('overview-generated-groups',groups.map(function(group){var folders=new Set((group.files||[]).map(function(file){return file.indexOf('/')>=0?file.split('/')[0]:'기본';}));return (group.platform==='ios'?'iOS':'Android')+' '+folders.size+'개 그룹';}).join(' · ')||'생성된 테스트 없음');
  var healingKnown=entries.length&&entries.every(function(entry){return typeof entry.healCount==='number';});
  set('overview-healing',healingKnown?entries.reduce(function(sum,entry){return sum+entry.healCount;},0):'—');
  set('overview-healing-context',entries.length?'최근 '+entries.length+'회 실행 기준'+(healingKnown?'':' · 복구 정보 없음'):'최근 10회 기준');
  set('overview-appium',status.appium?'연결됨':'미기동');
  var devices=Array.isArray(status.devices)?status.devices:[];
  set('overview-android-emulator',status.platform==='android'?(devices.filter(function(device){return /^emulator-/.test(device);}).join(', ')||'연결 없음'):'확인 전');
  set('overview-android-real',status.platform==='android'?(devices.filter(function(device){return !/^emulator-/.test(device);}).join(', ')||'연결 없음'):'확인 전');
  set('overview-ios',status.platform==='ios'?(devices.join(', ')||'연결 없음'):'확인 전');
  if(typeof _envOverviewSnapshot!=='undefined'&&_envOverviewSnapshot)renderOverviewEnvironment(_envOverviewSnapshot);
  var trend=document.getElementById('overview-trend');
  if(trend){trend.className=entries.length?'overview-trend-chart':'overview-trend-empty';trend.innerHTML=renderOverviewTrend();}
  var chart=document.getElementById('overview-rate-chart');if(chart)chart.innerHTML=renderOverviewRateChart(entries);
  set('overview-chart-context',entries.length?overviewDuration(entries[0].duration)+' · '+overviewResult(entries[0]).text:'실행 이력 없음');
  var stages={init:'대기',analyzed:'분석 완료',generated:'코드 생성 완료',linted:'검사 완료',executed:'실행 완료',healed:'자동 복구 완료'};
  var running=Array.isArray(status.running_steps)?status.running_steps:[];
  set('overview-pipeline-status',running.length?running.map(function(step){return STEP_LABEL[step]||step;}).join(' · ')+' 진행 중':stages[state.step]||'정보 없음');
  var quick=data.quickSummary||loadRunHistory().find(function(entry){return entry.type==='quick';});
  set('overview-quick-status',quick?overviewResult(quick).text+' '+(quick.passed||0)+'/'+(quick.total||0):'실행 없음');
  set('overview-report-status',state.report_path?'생성됨':'정보 없음');

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
    _overviewData={state:state,status:status,generated:generated,quickSummary:quickActive?Object.assign({},quickSummary,{status:'running'}):quickSummary};
    renderOverviewData(_overviewData);
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

var _tcStudioMounted = false;
async function refreshSelectedView(view, options){
  if(view === 'dashboard') return refreshOverview();
  if(view === 'reports') return refreshReports();
  if(view === 'history') return renderRunHistory();
  if(view === 'config') return pollEnvStatus();
  if(view === 'pipeline') return Promise.all([refreshStatus(),refreshTcFolders(),loadDevicePicker(getPlatform(), 'pipeline')]);
  if(view === 'capture'){
    pollEnvStatus();
    csMcpStatusPoll();
    if(!_csInitialized){ _csInitialized=true; csInit(); }
    return;
  }
  if(view === 'tests'){
    await Promise.all([refreshStatus(),refreshGenerated({navigation:true})]);
    if(!window._quickRunActive && !(options && options.preserveRun)) await _obsRenderCompletedQuickRun(_quickPlatform, true);
  }
  if(view === 'tc_studio' && _tcStudioMounted && window.TCS.refresh) return TCS.refresh();
}
function selectView(view, item, options){
  options = options || {};
  if(view !== 'tc_studio' && document.body.classList.contains('tc-studio-mode') &&
      !options.skipConfirm && window.TCS_NS && TCS_NS.detail){
    Promise.resolve(TCS_NS.detail.confirmLeave()).then(function(allowed){
      if(allowed) selectView(view, item, {skipConfirm:true, fromHistory:options.fromHistory, preserveRun:options.preserveRun});
      else if(options.fromHistory) history.pushState({}, '', '/tc-studio');
    });
    return;
  }
  if(!options.fromHistory){
    var viewUrl=new URL(location.href);
    viewUrl.pathname=view === 'tc_studio'?'/tc-studio':'/';
    if(view === 'dashboard'||view === 'tc_studio') viewUrl.searchParams.delete('view');
    else viewUrl.searchParams.set('view',view);
    var nextUrl=viewUrl.pathname+viewUrl.search+viewUrl.hash;
    if(nextUrl!==location.pathname+location.search+location.hash) history.pushState({}, '', nextUrl);
  }
  document.querySelectorAll('.sidebar-item').forEach(function(el){
    el.classList.toggle('active', el === item);
    if(el === item) el.setAttribute('aria-current','page');
    else el.removeAttribute('aria-current');
  });
  var grid=document.querySelector('.app-main > .grid');
  var pipeline=document.getElementById('view-pipeline');
  var overview=document.getElementById('view-overview');
  var studio=document.getElementById('tc-studio-root');
  var rightViews=['tests','reports','history','config','capture'];
  if(!grid || !pipeline) return;
  if(studio) studio.classList.toggle('view-hidden', view !== 'tc_studio');
  if(overview) overview.classList.toggle('view-hidden', view !== 'dashboard');
  grid.classList.toggle('view-hidden', view === 'dashboard' || view === 'tc_studio');
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
  if(main) main.classList.toggle('capture-view', view === 'capture');
  if(main) main.classList.toggle('quick-view', view === 'tests');
  if(main) main.classList.toggle('history-view', view === 'history');
  if(main) main.classList.toggle('tc-studio-view', view === 'tc_studio');
  document.body.classList.toggle('tc-studio-mode', view === 'tc_studio');
  if(view === 'tc_studio' && !_tcStudioMounted && window.TCS){
    _tcStudioMounted = true;
    TCS.init('#tc-studio-root').catch(function(error){
      studio.textContent = 'TC Studio를 불러오지 못했습니다: '+error.message;
      _tcStudioMounted = false;
    });
  }else{
    refreshSelectedView(view, options).catch(function(error){
      if(view === 'tc_studio' && window.TCS_NS) TCS_NS.toast(error.message, 'err');
    });
  }
  if(main) main.scrollTo({top:0, behavior:'smooth'});
}

window.addEventListener('popstate', function(){
  var view = location.pathname === '/tc-studio' ? 'tc_studio' :
    (new URLSearchParams(location.search).get('view') || 'dashboard');
  selectView(view, document.querySelector('.sidebar-item[data-view="'+view+'"]'), {fromHistory:true, preserveRun:location.hash.indexOf('#obs/')===0});
});

function loadRunHistory(){
  try{return JSON.parse(localStorage.getItem('qa-native-app.run-history')||'[]');}catch(_){return [];}
}
function renderRunHistory(){
  var entries=loadRunHistory(), list=document.getElementById('history-list');
  if(!list)return;
  list.innerHTML=entries.map(function(entry){
    var date=new Date(entry.executedAt||Date.now()), dateText=date.toLocaleDateString('ko-KR').replace(/\. /g,'-').replace(/\.$/,'');
    var time=date.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
    var groups=(entry.groups||[]).map(function(group){return '<span class="history-group">'+esc(group)+'</span>';}).join('');
    var ok=!entry.failed;
    return '<div class="history-row" data-history-type="'+esc(entry.type||'quick')+'" data-history-platform="'+esc(entry.platform||'android')+'" data-history-groups="'+esc((entry.groups||[]).join(' '))+'">'
      +'<div class="history-date"><strong>'+esc(dateText)+' '+esc(time)+'</strong></div>'
      +'<div><div class="history-pass" style="color:'+(ok?'var(--pass)':'var(--fail)')+'">'+entry.rate+'%</div><div class="history-progress"><span style="width:'+entry.rate+'%;background:'+(ok?'var(--pass)':'var(--fail)')+'"></span></div></div>'
      +'<div><span class="history-count">'+entry.passed+'<small> / '+entry.total+'</small></span></div><div class="history-duration">'+esc(entry.duration||'-')+'</div>'
      +'<div><span class="history-type">'+(entry.type==='pipeline'?'파이프라인 실행':'빠른 실행')+'</span></div><div><span class="history-platform '+esc(entry.platform||'android')+'">'+(entry.platform==='ios'?'iOS':'Android')+'</span></div>'
      +'<div class="history-groups">'+groups+'</div><div><span class="history-result" style="color:'+(ok?'var(--pass)':'var(--fail)')+';border-color:'+(ok?'var(--pass)':'var(--fail)')+'">'+(ok?'첫 시도 통과':'실패')+'</span></div></div>';
  }).join('')||'<div class="history-empty">실행 이력이 없습니다.</div>';
  var total=entries.length, passedRate=total?Math.round(entries.reduce(function(sum,item){return sum+(item.rate||0);},0)/total):0;
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

async function resetHistory(){
  if(!await dashboardConfirm('실행 히스토리를 초기화할까요?')) return;
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
    var groupMenu=e.target.closest('.history-group-menu');if(groupMenu){groupMenu.querySelector('summary').textContent=e.target.textContent;groupMenu.open=false;}
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
  var bar=document.getElementById('progress-bar');if(!bar)return;
  var doneCount=STEP_ORDER.filter(function(s){return _stepState[s]==='done';}).length;
  var labels={done:'완료',failed:'실패',running:'실행 중',idle:'대기',skipped:'건너뜀'};
  bar.innerHTML='<span class="pipeline-progress-count">'+doneCount+' / 5</span>';
  var count=document.getElementById('pipeline-step-count');if(count)count.textContent=doneCount+' / 5';
  STEP_ORDER.forEach(function(step){var badge=document.getElementById('step-status-'+step);if(badge){badge.textContent=labels[_stepState[step]]||'대기';badge.dataset.state=_stepState[step];}});
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
  if(!await dashboardConfirm('실행 중인 파이프라인을 중지하고 상태를 초기화할까요?')) return;
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
  if(!await dashboardConfirm('대시보드의 실행 요약, 로그와 누적 히스토리를 초기화할까요?\n생성 테스트와 리포트 파일은 유지됩니다.')) return;
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
