var _quickPlatform='android';

function setQuickPlatform(platform){
  if(platform!=='android'&&platform!=='ios') return;
  window._quickRunResultVisible=false;
  _quickPlatform=platform;
  updateAutomationStatus(platform);
  Promise.all([refreshStatus(),refreshGenerated()]).then(function(){
    _obsRenderCompletedQuickRun(platform);
  });
  loadDevicePicker(platform, 'quick');
}

async function refreshGenerated(){
  if(window._quickRunActive) return;
  if(window._quickRunResultVisible && !window._quickRunActive) return;
  try{
    var res=await fetch('/api/generated?platform='+encodeURIComponent(_quickPlatform)); var data=await res.json();
    window._generatedTests = data;
    var allHtml='', andHtml='', iosHtml='';
    data.forEach(function(g){
      var badge='<span class="gen-badge '+g.platform+'">'+(g.platform==='android'?'🤖':'🍎')+' '+g.platform+'</span>';
      var block='<div class="gen-item"><div>'+badge+'<span class="gen-count">'+g.count+'개 파일</span></div></div>';
      block+=g.files.map(function(file){
        var key=g.platform+':'+file.split('/')[0];
        return '<label class="quick-group-item"><input type="checkbox" class="quick-group-cb" value="'+esc(key)+'" checked>'
          +'<span class="quick-group-name">'+esc(key)+'</span><span class="quick-group-count">1개 파일</span></label>';
      }).join('');
      allHtml+=block;
      if(g.platform==='android') andHtml+=block;
      if(g.platform==='ios') iosHtml+=block;
    });
    var groupMap={};
    data.forEach(function(g){ g.files.forEach(function(file){ var key=g.platform+':'+file.split('/')[0]; (groupMap[key]||(groupMap[key]=[])).push({platform:g.platform,file:file}); }); });
    var groups=Object.keys(groupMap);
    var staleFiles=data.reduce(function(all,g){return all.concat(g.stale_files||[]);},[]);
    var staleHtml=staleFiles.length
      ? '<div class="env-error-banner">⚠️ 구버전 테스트 '+staleFiles.length+'개가 감지되었습니다. Capture Studio에서 다시 저장·생성한 뒤 실행하세요.</div>'
      : '';
    var folderHtml=groups.map(function(key){ return '<label class="quick-group-item"><input type="checkbox" class="quick-group-cb" value="'+esc(key)+'" checked onchange="syncQuickSelection()">'
      +'<span class="quick-group-name">'+esc(key.split(':').slice(1).join(':'))+'</span><span class="quick-group-count">'+groupMap[key].length+'개 파일</span></label>'; }).join('');
    // Legacy result cards are no longer restored; the observability workspace
    // is reconstructed from the latest server-side run manifest instead.
    try{ localStorage.removeItem('qa-native-app.quick-result-v3.'+_quickPlatform); }catch(_){ }
    window._quickRunResultVisible=false;
    var quickHtml='<div class="quick-view-head"><div><div class="quick-view-title">빠른 실행</div><p class="quick-view-subtitle">선택한 OS의 tests/generated 폴더에 생성된 테스트 코드만 실행합니다.</p></div>'
      +'<button type="button" class="reset-btn" onclick="resetQuickRun()">↺ 리셋</button></div>'+staleHtml
      +'<div class="quick-platform-selector"><button type="button" class="quick-platform-btn '+(_quickPlatform==='android'?'active':'')+'" onclick="setQuickPlatform(\'android\')">🤖 Android</button><button type="button" class="quick-platform-btn '+(_quickPlatform==='ios'?'active':'')+'" onclick="setQuickPlatform(\'ios\')">🍎 iOS</button></div>'
      +'<div class="device-picker" style="margin-bottom:14px"><div class="device-picker-head"><span>디바이스 선택</span><button onclick="refreshDevicePicker()">↻ 새로고침</button></div><div id="quick-device-hint" class="device-hint none" style="display:none"></div><div id="quick-device-list"><div style="font-size:11px;color:var(--text3)">로딩 중...</div></div></div>'
      +'<div id="obs-strip-quick">'+_obsStripHtml()+'</div>'
      +'<div class="quick-select-card"><div class="quick-select-head"><span>'+(_quickPlatform==='android'?'Android':'iOS')+' 테스트 폴더</span><label><input type="checkbox" id="quick-select-all" checked onchange="quickToggleGenerated(this.checked)"> 전체 선택</label></div>'
      +'<div class="quick-group-list">'+(folderHtml||'<div class="tc-folder-empty">생성된 테스트 폴더가 없습니다.</div>')+'</div>'
      +'<div class="quick-action-row"><button class="quick-run-action" id="quick-generated-run" onclick="runSelectedGenerated()" '+(!groups.length?'disabled':'')+'>테스트 실행</button><label><input type="checkbox" id="generated-heal" checked> 힐링 생략</label><span id="quick-run-status" class="quick-run-status"></span></div></div>'
      +'<div id="quick-generated-log-wrap" class="quick-log-wrap" style="display:none"><div class="quick-log-head"><span>실행 로그</span><span class="quick-log-actions"><button type="button" onclick="toggleQuickLog()">접기</button><button type="button" onclick="clearQuickLog()">지우기</button></span></div><div id="quick-generated-log" class="quick-log"></div></div><div id="quick-generated-result"></div>';
    document.getElementById('gen-all').innerHTML=quickHtml||'<div class="empty">없음</div>';
    document.getElementById('gen-android').innerHTML=andHtml||'<div class="empty">없음</div>';
    document.getElementById('gen-ios').innerHTML=iosHtml||'<div class="empty">없음</div>';
    setupQuickCasePagination(document.getElementById('quick-generated-result'));
    // 빠른 실행 HTML 재렌더 후 디바이스 피커 재주입
    loadDevicePicker(_quickPlatform, 'quick');
  }catch(_){}
}

function quickToggleGenerated(checked){
  document.querySelectorAll('.quick-group-list .quick-group-cb').forEach(function(cb){ cb.checked=checked; });
}
function syncQuickSelection(){
  var all=document.querySelectorAll('.quick-group-list .quick-group-cb'), selected=document.querySelectorAll('.quick-group-list .quick-group-cb:checked');
  var toggle=document.getElementById('quick-select-all');
  if(toggle) toggle.checked=all.length>0 && all.length===selected.length;
}

function _setQuickRunCompletionStatus(statusEl, completedCount, failedCount){
  if(!statusEl) return;
  statusEl.className='quick-run-status '+(failedCount?'fail':'done');
  statusEl.textContent=failedCount
    ? '● '+completedCount+'개 실행 완료 · '+failedCount+'개 실패'
    : '● '+completedCount+'개 실행 완료 · 모두 통과';
}

async function runSelectedGenerated(){
  var keys=Array.from(document.querySelectorAll('.quick-group-list .quick-group-cb:checked')).map(function(cb){return cb.value;});
  var all=(window._generatedTests||[]), groups=[];
  all.forEach(function(g){
    // 폴더별로 개별 그룹 생성 — 여러 폴더를 하나로 묶으면 첫 번째 폴더만 실행되는 버그 방지
    var folderMap={};
    g.files.forEach(function(file){
      var folder=file.split('/')[0];
      var k=g.platform+':'+folder;
      if(keys.indexOf(k)!==-1){
        if(!folderMap[folder]) folderMap[folder]={platform:g.platform,folder:folder,files:[]};
        folderMap[folder].files.push(file);
      }
    });
    Object.keys(folderMap).forEach(function(folder){groups.push(folderMap[folder]);});
  });
  var files=groups.reduce(function(acc,g){return acc.concat(g.files.map(function(file){return {platform:g.platform,file:file};}));},[]);
  if(!files.length){ setLog('[안내] 실행할 테스트 폴더를 선택하세요.'); return; }
  var btn=document.getElementById('quick-generated-run'); if(btn){btn.disabled=true;btn.textContent='실행 중...';}
  var statusEl=document.getElementById('quick-run-status');
  if(statusEl){statusEl.className='quick-run-status running';statusEl.textContent='● 테스트 실행 중';}
  var noHeal=document.getElementById('generated-heal')?.checked === true;
  window._quickRunActive=true;
  try{localStorage.setItem('qa-native-app.quick-active.'+_quickPlatform,JSON.stringify({platform:_quickPlatform,total:files.length,passed:0,failed:0,current:0,startedAt:new Date().toISOString()}));}catch(_){ }
  var passed=0, failed=0, done=0, groupStats={}, caseResults=[];
  var logEl=document.getElementById('quick-generated-log'), logWrap=document.getElementById('quick-generated-log-wrap'), resultEl=document.getElementById('quick-generated-result');
  window._quickRunLogEl=logEl;
  window._quickRunLogWrap=logWrap;
  if(logWrap) logWrap.style.display='block';
  if(logEl) logEl.textContent='';
  if(resultEl) resultEl.innerHTML='';
  for(var i=0;i<groups.length;i++){
    var group=groups[i], groupKey=group.platform+':'+group.folder;
    groupStats[groupKey]={total:group.files.length,passed:0,failed:0};
    if(statusEl) statusEl.textContent='● 테스트 실행 중';
    if(logEl) logEl.textContent+='['+(i+1)+'/'+groups.length+'] '+group.platform+'/'+group.folder+' ('+group.files.length+'개 TC)\n';
    try{localStorage.setItem('qa-native-app.quick-live-log.'+_quickPlatform,logEl?logEl.textContent:'');}catch(_){ }
    var result=await executeGeneratedFolder(group.platform,group.folder,!noHeal);
    var resultData=result.result||{}, passedFiles=(resultData.passed||[]).map(function(file){return String(file).replace(/\\/g,'/').split('::')[0];});
    var errorFiles=(resultData.errors||[]).map(function(entry){return String(entry.file||'').replace(/\\/g,'/').split('::')[0];});
    group.files.forEach(function(file){
      var casePassed=result.ok && result.exit_code===0 && !errorFiles.some(function(error){return error.endsWith('/'+file)||error.endsWith(file);});
      if(passedFiles.length) casePassed=passedFiles.some(function(passedFile){return passedFile.endsWith('/'+file)||passedFile.endsWith(file);});
      if(casePassed){passed++;groupStats[groupKey].passed++;}else{failed++;groupStats[groupKey].failed++;}
      done++;caseResults.push({platform:group.platform,file:file,passed:casePassed});
    });
    try{localStorage.setItem('qa-native-app.quick-active.'+_quickPlatform,JSON.stringify({platform:_quickPlatform,total:files.length,passed:passed,failed:failed,current:done,startedAt:new Date().toISOString()}));localStorage.setItem('qa-native-app.quick-live-log.'+_quickPlatform,logEl?logEl.textContent:'');}catch(_){ }
  }
  var rate=done?Math.round(passed/done*100):0;
  if(resultEl) resultEl.innerHTML='<div class="obs-workspace-loading">실행 증거를 불러오는 중...</div>';
  try{
    localStorage.removeItem('qa-native-app.quick-result-v3.'+_quickPlatform);
    localStorage.setItem('qa-native-app.quick-summary.'+_quickPlatform,JSON.stringify({platform:_quickPlatform,total:done,passed:passed,failed:failed,rate:rate,noHeal:noHeal,executedAt:new Date().toISOString()}));
  }catch(_){ }
  recordRunHistory({type:'quick',platform:_quickPlatform,total:done,passed:passed,failed:failed,rate:rate,groups:Object.keys(groupStats).map(function(key){return key.split(':').slice(1).join(':');}),healCount:noHeal?0:0,executedAt:new Date().toISOString()});
  window._quickRunResultVisible=true;
  if(btn){btn.disabled=false;btn.textContent='테스트 실행';}
  try{localStorage.setItem('qa-native-app.quick-log.'+_quickPlatform,logEl?logEl.textContent:'');}catch(_){ }
  try{localStorage.removeItem('qa-native-app.quick-active.'+_quickPlatform);localStorage.removeItem('qa-native-app.quick-live-log.'+_quickPlatform);}catch(_){ }
  if(logWrap){logWrap.style.display='block';}
  _setQuickRunCompletionStatus(statusEl,done,failed);
  window._quickRunLogEl=null;
  window._quickRunLogWrap=null;
  window._quickRunActive=false;
  // 대시보드 KPI·히스토리 뷰 갱신
  refreshOverview();
  renderRunHistory();
  // 기존 결과 카드 없이 목업형 관측성 워크스페이스만 렌더링한다.
  await _obsRenderCompletedQuickRun(_quickPlatform);
}

async function toggleQuickCaseDetail(button){
  if(!button) return;
  var caseWrap=button.closest('.quick-folder-case');
  var detail=caseWrap?caseWrap.querySelector('.quick-case-detail'):button.querySelector('.quick-case-detail');
  if(!detail) return;
  var openTarget=caseWrap||button;
  var isOpen=openTarget.classList.toggle('open');
  if(!isOpen) return;
  if(button.dataset.loaded==='true') return;
  try{
    var query='?platform='+encodeURIComponent(button.dataset.platform)+'&file='+encodeURIComponent(button.dataset.file);
    var res=await fetch('/api/testcase'+query); var data=await res.json();
    detail.textContent=data.ok?data.content:(data.error||'Markdown TC를 불러오지 못했습니다.');
    button.dataset.loaded='true';
  }catch(_){ detail.textContent='Markdown TC를 불러오지 못했습니다.'; }
}

function toggleQuickFolderResult(button){
  var folder=button&&button.closest('.quick-folder-result');
  if(folder) folder.classList.toggle('open');
}

function filterQuickFolderCases(button,filter){
  var folder=button&&button.closest('.quick-folder-result');
  if(!folder) return;
  folder.querySelectorAll('.quick-folder-filter').forEach(function(item){item.classList.toggle('active',item===button);});
  folder.querySelectorAll('.quick-folder-case').forEach(function(item){
    item.classList.toggle('hidden',filter!=='all'&&item.dataset.result!==filter);
  });
}

function formatQuickCaseName(file){
  return String(file||'').split('/').pop().replace(/\.py$/,'').replace(/^tc_?\d+_/i,'').replace(/^ApiDemos_/i,'').replace(/_/g,' ');
}

function setupQuickCasePagination(root){
  if(!root) return;
  var list=root.querySelector('.quick-case-results');
  if(!list) return;
  var rows=Array.from(list.querySelectorAll('.quick-case-result'));
  var oldPager=root.querySelector('.quick-case-pager');
  if(oldPager) oldPager.remove();
  var pageSize=10, pageCount=Math.max(1,Math.ceil(rows.length/pageSize));
  if(!rows.length) return;
  var pager=document.createElement('div'); pager.className='quick-case-pager';
  var page=1;
  function render(){
    rows.forEach(function(row,index){row.style.display=(index >= (page-1)*pageSize && index < page*pageSize)?'block':'none';});
    pager.innerHTML='<button type="button" '+(page===1?'disabled':'')+' onclick="this.closest(\'.quick-case-pager\')._move(-1)">이전</button><span>'+page+' / '+pageCount+'</span><button type="button" '+(page===pageCount?'disabled':'')+' onclick="this.closest(\'.quick-case-pager\')._move(1)">다음</button>';
  }
  pager._move=function(delta){page=Math.max(1,Math.min(pageCount,page+delta));render();};
  list.parentNode.appendChild(pager); render();
}

function resetQuickRun(){
  var resultEl=document.getElementById('quick-generated-result');
  var logEl=document.getElementById('quick-generated-log'), logWrap=document.getElementById('quick-generated-log-wrap');
  var statusEl=document.getElementById('quick-run-status');
  var btn=document.getElementById('quick-generated-run');
  if(resultEl) resultEl.innerHTML='';
  if(logEl) logEl.textContent='';
  if(logWrap) logWrap.style.display='none';
  if(statusEl){statusEl.className='quick-run-status';statusEl.textContent='';}
  if(btn){btn.disabled=document.querySelectorAll('.quick-group-list .quick-group-cb:checked').length===0;btn.textContent='테스트 실행';}
  window._quickRunLogEl=null;
  window._quickRunLogWrap=null;
  window._quickRunResultVisible=false;
  try{localStorage.removeItem('qa-native-app.quick-result-v3.'+_quickPlatform);localStorage.removeItem('qa-native-app.quick-summary.'+_quickPlatform);localStorage.removeItem('qa-native-app.quick-log.'+_quickPlatform);localStorage.removeItem('qa-native-app.quick-active.'+_quickPlatform);localStorage.removeItem('qa-native-app.quick-live-log.'+_quickPlatform);}catch(_){ }
}

function toggleQuickLog(){
  var wrap=document.getElementById('quick-generated-log-wrap');
  if(!wrap) return;
  wrap.classList.toggle('collapsed');
  var button=wrap.querySelector('.quick-log-actions button');
  if(button) button.textContent=wrap.classList.contains('collapsed')?'펼치기':'접기';
}
function clearQuickLog(){
  var log=document.getElementById('quick-generated-log');
  var wrap=document.getElementById('quick-generated-log-wrap');
  if(log) log.textContent='';
  if(wrap) wrap.style.display='none';
  // 실행 중이더라도 로그 참조를 끊어 폴링이 숨겨진 영역을 업데이트하지 않도록
  window._quickRunLogEl=null;
  window._quickRunLogWrap=null;
  try{localStorage.removeItem('qa-native-app.quick-log.'+_quickPlatform);localStorage.removeItem('qa-native-app.quick-live-log.'+_quickPlatform);}catch(_){ }
}

async function runGeneratedFile(platform, file){
  var noHeal=document.getElementById('generated-heal')?.checked === true;
  return executeGeneratedFile(platform,file,!noHeal);
}
function executeGeneratedFile(platform,file,heal,folder){
  return new Promise(async function(resolve){
    try{
    var res=await fetch('/api/run_test',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.assign({platform:platform,heal:heal,obs_keep:_obsKeep},folder?{test_folder:folder}:{test_file:file},getSelectedDeviceParams()))});
    var data=await res.json();
    if(!data.ok){
      if(window._quickRunLogEl) window._quickRunLogEl.textContent='[오류] '+(data.error||'실행 실패');
      resolve({ok:false,exit_code:1}); return;
    }
    var logName=data.log;
    var timer=setInterval(async function(){
    try{
      var res=await fetch('/api/run_log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({log:logName})});
      var data=await res.json();
      if(data.ok){
        var liveLog=data.log||'실행 중...';
        if(window._quickRunLogEl){
          if(window._quickRunLogWrap) window._quickRunLogWrap.style.display='block';
          window._quickRunLogEl.textContent=liveLog;
          window._quickRunLogEl.scrollTop=window._quickRunLogEl.scrollHeight;
        }
      }
      if(data.done){
        clearInterval(timer); refreshStatus(); refreshReports();
        if(!window._quickRunActive) refreshGenerated();
        resolve(data);
      }
    }catch(_){ }
    },1000);
    }catch(err){
      if(window._quickRunLogEl) window._quickRunLogEl.textContent='[요청 실패] '+err.message;
      resolve({ok:false,exit_code:1});
    }
  });
}

function executeGeneratedFolder(platform,folder,heal){
  return executeGeneratedFile(platform,'',heal,folder);
}
