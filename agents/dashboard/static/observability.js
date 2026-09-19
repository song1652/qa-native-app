// ══════════════════════════════════════════════════════════════
// 증거 수집 관측성 (Execution Observability — PRD §8)
// ══════════════════════════════════════════════════════════════
var _obsKeep = (function(){
  try{ return localStorage.getItem('qa-native-app.obs-keep')||'on_failure'; }catch(_){ return 'on_failure'; }
})();

function _obsSetKeep(v){
  if(v!=='on_failure'&&v!=='always') return;
  _obsKeep=v;
  try{ localStorage.setItem('qa-native-app.obs-keep',v); }catch(_){}
  _obsRenderStrips();
}

function _obsStripHtml(stripId){
  var always=_obsKeep==='always';
  var groupName='obs-keep-radio-'+String(stripId||'default');
  var feedback=always?'성공 포함 모든 증거 보존 · 약 33 MB/run':'실패·FLAKY 증거만 보존 · 약 17 MB/run';
  return '<div class="obs-strip">'
    +'<span class="obs-strip-label"><span class="obs-strip-bulb"></span>증거 수집</span>'
    +'<span class="obs-collect-chips"><span class="obs-collect-chip">▶ 영상</span><span class="obs-collect-chip">▤ 로그</span></span>'
    +'<span style="font-size:10.5px;color:var(--text3)">항상 수집 · 보존 정책</span>'
    +'<div class="obs-radio-row" role="radiogroup" aria-label="보존 정책">'
    +'<label class="obs-policy-option '+(!always?'is-selected':'')+'" role="radio" aria-checked="'+(!always)+'"><input type="radio" name="'+groupName+'" data-obs-keep-radio value="on_failure" '
    +(!always?'checked':'')+' onchange="_obsSetKeep(\'on_failure\')"><span class="obs-policy-check">'+(!always?'✓':'')+'</span>실패 시만</label>'
    +'<label class="obs-policy-option '+(always?'is-selected':'')+'" role="radio" aria-checked="'+always+'"><input type="radio" name="'+groupName+'" data-obs-keep-radio value="always" '
    +(always?'checked':'')+' onchange="_obsSetKeep(\'always\')"><span class="obs-policy-check">'+(always?'✓':'')+'</span>항상</label>'
    +'</div>'
    +'<span class="obs-policy-feedback">'+feedback+'</span>'
    +'</div>';
}

function _obsRenderStrips(){
  var ids=['obs-strip-pipeline','obs-strip-quick'];
  ids.forEach(function(id){
    var el=document.getElementById(id);
    if(el) el.innerHTML=_obsStripHtml(id);
  });
  // 이미 렌더된 라디오 동기화 (refreshGenerated 내부 동적 스트립)
  document.querySelectorAll('input[data-obs-keep-radio]').forEach(function(r){
    r.checked = r.value===_obsKeep;
  });
}

// 아티팩트 도트 HTML (kept=true & 각 타입 존재 여부)
function _artDotsHtml(hasVideo, hasLog, hasShot, isFail){
  var cls = isFail ? 'fail-on' : 'on';
  return '<span class="art-dots">'
    +'<span class="art-dot '+(hasVideo?cls:'')+'" title="영상">▶</span>'
    +'<span class="art-dot '+(hasLog?cls:'')+'" title="로그">▤</span>'
    +'<span class="art-dot '+(hasShot?cls:'')+'" title="스크린샷">▣</span>'
    +'</span>';
}

// ── 증거 상세 오버레이 ─────────────────────────────────────
var _evState = {runId:null, nodeid:null, manifest:null, tab:'video', attempt:null};

function openEvDetail(runId, nodeid, manifest){
  _evState.runId=runId; _evState.nodeid=nodeid; _evState.manifest=manifest; _evState.tab='video'; _evState.attempt=null;
  _evLogRaw=[]; _evLogLvlActive='ALL'; _evLogQ='';
  _evRender();
  document.getElementById('ev-detail-overlay').classList.add('open');
}

function _evSelection(){
  var manifest=_evState.manifest||{};
  var entry=(manifest.entries||[]).find(function(e){return e.nodeid===_evState.nodeid;})||{};
  var attempts=(entry.attempts&&entry.attempts.length)?entry.attempts:[entry];
  if(_evState.attempt===null&&attempts.length) _evState.attempt=attempts[attempts.length-1].n||attempts.length;
  var attempt=attempts.find(function(a){return (a.n||1)===_evState.attempt;})||attempts[attempts.length-1]||{};
  return {entry:entry,attempts:attempts,attempt:attempt};
}

function _evSelectAttempt(n){
  _evState.attempt=n;
  _evRender();
}

function _evEvidenceReason(attempt, kind){
  var errors=attempt.collect_errors||[];
  var messages={
    no_device:'연결된 대상 기기를 찾지 못했습니다.',
    video_unsupported:'이 기기는 화면 녹화를 지원하지 않습니다.',
    video_start_failed:'화면 녹화를 시작하지 못했습니다.',
    video_pull_failed:'기기에서 녹화 파일을 가져오지 못했습니다.',
    video_invalid:'녹화 파일이 손상되었거나 재생 시간이 없습니다.',
    video_stop_timeout:'화면 녹화 종료가 제한 시간을 초과했습니다.',
    ios_real_device_unsupported:'iOS 실기기 증거 수집은 현재 지원하지 않습니다.',
    ios_log_bundle_id_missing:'iOS 앱 Bundle ID가 없어 로그 필터를 만들 수 없습니다.',
    syslog_start_failed:'시스템 로그 수집을 시작하지 못했습니다.'
  };
  var relevant=errors.find(function(code){
    if(!messages[code]) return false;
    if(code==='no_device'||code==='ios_real_device_unsupported') return true;
    if(kind==='video') return code.indexOf('video_')===0;
    return code.indexOf('syslog_')===0||code==='ios_log_bundle_id_missing';
  });
  if(relevant) return messages[relevant];
  if(!attempt.kept) return '보존 정책에 따라 이 시도의 증거를 저장하지 않았습니다.';
  return kind==='video'?'영상이 없습니다.':'시스템 로그가 없습니다.';
}

function closeEvDetail(){
  document.getElementById('ev-detail-overlay').classList.remove('open');
}

function _evRender(){
  var runId=_evState.runId, nodeid=_evState.nodeid;
  var manifest=_evState.manifest||{};
  var selection=_evSelection(), entry=selection.entry, attempt=selection.attempt;
  var outcome=attempt.outcome||entry.outcome||'unknown';
  var kept=attempt.kept;

  // 배지
  var badge=document.getElementById('ev-dialog-badge');
  var nodeEl=document.getElementById('ev-dialog-node');
  if(badge) badge.innerHTML='<span style="padding:2px 9px;border-radius:5px;font-size:10px;font-weight:700;'+(outcome==='failed'?'color:var(--fail);background:rgba(251,113,133,.14);border:1px solid rgba(251,113,133,.3)':'color:var(--pass);background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.3)')+'">'+outcome.toUpperCase()+'</span>';
  if(nodeEl) nodeEl.textContent=nodeid;

  var hasVideo=kept&&attempt.video;
  var hasLog=kept&&attempt.syslog;
  var hasShot=kept&&attempt.screenshot;

  // 탭
  var tabs=document.getElementById('ev-dialog-tabs');
  if(tabs){
    var attemptHtml=selection.attempts.length>1?'<span style="display:flex;align-items:center;gap:4px;margin-right:10px;font-size:10px;color:var(--text3)">시도 '+selection.attempts.map(function(a){var n=a.n||1;return '<button type="button" class="ev-lvl '+(n===_evState.attempt?'active':'')+'" onclick="_evSelectAttempt('+n+')">'+n+'</button>';}).join('')+'</span>':'';
    tabs.innerHTML=attemptHtml+['video','log','shot'].map(function(t){
      var labels={video:'▶ 영상',log:'▤ 시스템 로그',shot:'▣ 스크린샷'};
      var has={video:hasVideo,log:hasLog,shot:hasShot};
      return '<button type="button" class="ev-dialog-tab'+(t===_evState.tab?' active':'')
        +'" '+(has[t]?'':'disabled')+' onclick="_evTab(\''+t+'\')" data-ev="'+t+'">'+labels[t]+'</button>';
    }).join('');
  }

  _evTabBody();
}

function _evTab(t){
  _evState.tab=t;
  document.querySelectorAll('.ev-dialog-tab').forEach(function(b){
    b.classList.toggle('active',b.dataset.ev===t);
  });
  _evTabBody();
}

function _evTabBody(){
  var body=document.getElementById('ev-dialog-body');
  if(!body) return;
  var runId=_evState.runId, nodeid=_evState.nodeid;
  var manifest=_evState.manifest||{};
  var selection=_evSelection(), entry=selection.entry, attempt=selection.attempt;
  var kept=attempt.kept;
  var encId=encodeURIComponent(nodeid);
  var attemptN=attempt.n||1;

  if(_evState.tab==='video'){
    if(kept&&attempt.video){
      var offsetSec=attempt.failure_offset_sec||0;
      var videoUrl=attempt.video_url||('/api/run_artifacts/'+encodeURIComponent(runId)+'/video?nodeid='+encId+'&attempt='+attemptN);
      body.innerHTML='<video id="ev-video-el" class="ev-video-tag" controls preload="metadata" src="'+esc(videoUrl)+'"></video>'
        +'<div class="ev-shot-meta">실패 지점: '+offsetSec+'초 · H.264 · HTTP Range 지원</div>';
      setTimeout(function(){
        var v=document.getElementById('ev-video-el');
        if(v&&offsetSec) v.addEventListener('loadedmetadata',function(){v.currentTime=offsetSec;},{once:true});
      },100);
    } else {
      body.innerHTML='<div class="ev-no-evidence">'+esc(_evEvidenceReason(attempt,'video'))+'</div>';
    }
  } else if(_evState.tab==='log'){
    if(kept&&attempt.syslog){
      var appPreset=manifest.app_id?'<button type="button" class="ev-lvl" onclick="_evPreset(decodeURIComponent(\''+encodeURIComponent(manifest.app_id)+'\'))">앱</button>':'';
      body.innerHTML='<div class="ev-log-toolbar">'
        +'<input type="text" class="ev-log-search" id="ev-log-q" placeholder="로그 검색" oninput="_evLogFilter()">'
        +'<button type="button" class="ev-lvl active" data-l="ALL" onclick="_evLogLvl(this,\'ALL\')">전체</button>'
        +'<button type="button" class="ev-lvl" data-l="E" onclick="_evLogLvl(this,\'E\')">E/</button>'
        +'<button type="button" class="ev-lvl" data-l="W" onclick="_evLogLvl(this,\'W\')">W/</button>'
        +'<button type="button" class="ev-lvl" data-l="FATAL" onclick="_evLogLvl(this,\'FATAL\')">FATAL</button>'
        +'<button type="button" class="ev-lvl" onclick="_evPreset(\'AndroidRuntime\')">AndroidRuntime</button>'
        +appPreset
        +'</div>'
        +'<div class="ev-logbox" id="ev-logbox"><div style="padding:10px;color:var(--text3);font-size:11px">로딩 중...</div></div>'
        +'<div class="ev-log-foot" id="ev-log-foot"></div>';
      _evLoadLog(runId, nodeid, encId, attemptN, attempt.syslog_url);
    } else {
      body.innerHTML='<div class="ev-no-evidence">'+esc(_evEvidenceReason(attempt,'log'))+'</div>';
    }
  } else {
    if(kept&&attempt.screenshot&&attempt.screenshot.path){
      var p=attempt.screenshot.path;
      var src=p.startsWith('reports/screenshots/')?'/screenshots/'+p.slice('reports/screenshots/'.length):'/screenshots/'+p;
      body.innerHTML='<img class="ev-shot-img" src="'+esc(src)+'" alt="실패 스크린샷">'
        +'<div class="ev-shot-meta">경로: '+esc(p)+'</div>';
    } else {
      body.innerHTML='<div class="ev-no-evidence">스크린샷이 없습니다.</div>';
    }
  }
}

var _evLogRaw=[], _evLogLvlActive='ALL', _evLogQ='';

function _evLoadLog(runId, nodeid, encId, attemptN, suppliedUrl){
  var url=suppliedUrl||('/api/run_artifacts/'+encodeURIComponent(runId)+'/logcat?nodeid='+encId+'&attempt='+attemptN+'&tail=2000');
  fetch(url)
    .then(function(r){return r.text();})
    .then(function(txt){
      _evLogRaw=txt.split('\n');
      _evLogRenderLines();
    })
    .catch(function(){ var b=document.getElementById('ev-logbox'); if(b) b.innerHTML='<div style="padding:10px;color:var(--fail);font-size:11px">로그 로드 실패</div>'; });
}

function _evPreset(value){
  var q=document.getElementById('ev-log-q');
  if(q) q.value=value;
  _evLogQ=value;
  _evLogRenderLines();
}

function _evLogFilter(){
  var q=document.getElementById('ev-log-q');
  if(q) _evLogQ=q.value;
  _evLogRenderLines();
}

function _evLogLvl(btn, lvl){
  _evLogLvlActive=lvl;
  document.querySelectorAll('.ev-lvl').forEach(function(b){b.classList.toggle('active',b.dataset.l===lvl);});
  _evLogRenderLines();
}

function _evLogRenderLines(){
  var box=document.getElementById('ev-logbox');
  if(!box) return;
  var rows=_evLogRaw.filter(function(line){
    if(!line.trim()) return false;
    if(_evLogLvlActive!=='ALL'){
      // 레벨 필터: "14:31:02.114  I  태그:" 형태 — 3번째 공백구분 토큰이 레벨
      var parts=line.split(/\s+/);
      if(_evLogLvlActive==='E'||_evLogLvlActive==='W'){
        var lvlTok=parts[2]||parts[1]||'';
        if(lvlTok!==_evLogLvlActive) return false;
      } else {
        if(line.indexOf(_evLogLvlActive)<0) return false;
      }
    }
    if(_evLogQ && line.toLowerCase().indexOf(_evLogQ.toLowerCase())<0) return false;
    return true;
  });
  var html=rows.slice(-500).map(function(line){
    var m=line.match(/^(\S+\s+\S+)\s+(\w)\s+(.*)$/);
    var t='', l='', msg=esc(line), lvlCls='';
    if(m){t=esc(m[1]);l=esc(m[2]);msg=_evHilight(esc(m[3]));lvlCls=l;}
    return '<div class="ev-logline '+(lvlCls||'')+'">'
      +'<span class="ev-lg-t">'+t+'</span>'
      +'<span class="ev-lg-l">'+l+'</span>'
      +'<span class="ev-lg-m">'+msg+'</span>'
      +'</div>';
  }).join('');
  box.innerHTML=html||'<div style="padding:10px;color:var(--text3);font-size:11px">일치하는 줄 없음</div>';
  box.scrollTop=box.scrollHeight;
  var foot=document.getElementById('ev-log-foot');
  if(foot) foot.innerHTML='<span>'+rows.length+' / '+_evLogRaw.length+' 줄 표시</span><span>·</span><span>tail 2000줄</span>';
}

function _evHilight(text){
  if(!_evLogQ) return text;
  return text.replace(new RegExp('('+_evLogQ.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),'<mark>$1</mark>');
}

// ── 목업형 실행 증거 워크스페이스 ──────────────────────────
var _obsWorkspace={runId:null,manifest:null,nodeid:null,attempt:null,tab:'video',caseFilter:'all',casePage:1};
var _obsCasePageSize=10;

function _obsEntryAttempts(entry){
  return (entry.attempts&&entry.attempts.length)?entry.attempts:[entry];
}

function _obsLatestAttempt(entry){
  var attempts=_obsEntryAttempts(entry);
  return attempts[attempts.length-1]||{};
}

function _obsShortNode(nodeid){
  var parts=String(nodeid||'').split('::');
  var file=(parts[0]||'').split('/').pop().replace(/\.py$/,'');
  return file+(parts.length>1?'::'+parts[parts.length-1]:'');
}

function _obsFormatBytes(bytes){
  var value=Number(bytes)||0;
  if(value>=1024*1024) return (value/(1024*1024)).toFixed(1)+' MB';
  if(value>=1024) return (value/1024).toFixed(1)+' KB';
  return value+' B';
}

function _obsFormatDuration(seconds){
  var value=Number(seconds)||0;
  return value.toFixed(1)+'s';
}

function _obsEntryStatus(entry){
  var attempts=_obsEntryAttempts(entry), latest=attempts[attempts.length-1]||{};
  var priorFailed=attempts.slice(0,-1).some(function(a){return a.outcome==='failed'||a.outcome==='error';});
  if(latest.outcome==='passed'&&priorFailed) return {key:'flaky',label:'FLAKY'};
  if(latest.outcome==='failed'||latest.outcome==='error') return {key:'fail',label:'FAIL'};
  return {key:'pass',label:'PASS'};
}

function _obsAttemptUrl(kind,runId,nodeid,attempt){
  var supplied=kind==='video'?attempt.video_url:attempt.syslog_url;
  if(supplied) return supplied;
  var endpoint=kind==='video'?'video':'logcat';
  return '/api/run_artifacts/'+encodeURIComponent(runId)+'/'+endpoint
    +'?nodeid='+encodeURIComponent(nodeid)+'&attempt='+(attempt.n||1)
    +(kind==='log'?'&tail=2000':'');
}

function _obsDefaultNode(manifest){
  var entries=manifest.entries||[];
  var failed=entries.find(function(entry){
    var latest=_obsLatestAttempt(entry);
    return (latest.outcome==='failed'||latest.outcome==='error')
      &&latest.kept&&(latest.video||latest.syslog||latest.screenshot);
  });
  return (failed||entries[0]||{}).nodeid||null;
}

function _obsEntryMatchesCaseFilter(entry,filter){
  var latest=_obsLatestAttempt(entry), outcome=latest.outcome;
  if(filter==='pass') return outcome==='passed';
  if(filter==='fail') return outcome==='failed'||outcome==='error';
  return true;
}

function _obsSetCaseFilter(filter){
  if(filter!=='all'&&filter!=='pass'&&filter!=='fail') return;
  _obsWorkspace.caseFilter=filter;
  _obsWorkspace.casePage=1;
  var entries=(_obsWorkspace.manifest&&_obsWorkspace.manifest.entries)||[];
  var filtered=entries.filter(function(item){return _obsEntryMatchesCaseFilter(item,filter);});
  if(!filtered.some(function(item){return item.nodeid===_obsWorkspace.nodeid;})){
    _obsWorkspace.nodeid=(filtered[0]||{}).nodeid||null;
    _obsWorkspace.attempt=null;
    _obsWorkspace.tab='video';
  }
  _obsRenderWorkspace(_obsWorkspace.runId,_obsWorkspace.manifest,_obsWorkspace.nodeid);
}

function _obsSetCasePage(page){
  _obsWorkspace.casePage=Math.max(1,Number(page)||1);
  _obsRenderWorkspace(_obsWorkspace.runId,_obsWorkspace.manifest,_obsWorkspace.nodeid);
}

function _obsRenderWorkspace(runId,manifest,nodeid){
  var root=document.getElementById('quick-generated-result');
  if(!root) return;
  window._quickRunResultVisible=true;
  var sameRun=_obsWorkspace.runId===runId;
  _obsWorkspace.runId=runId;
  _obsWorkspace.manifest=manifest;
  if(!sameRun){_obsWorkspace.caseFilter='all';_obsWorkspace.casePage=1;}
  _obsWorkspace.nodeid=nodeid||(sameRun&&_obsWorkspace.nodeid)||_obsDefaultNode(manifest);
  var entry=(manifest.entries||[]).find(function(item){return item.nodeid===_obsWorkspace.nodeid;});
  if(!entry){_obsWorkspace.nodeid=_obsDefaultNode(manifest);entry=(manifest.entries||[]).find(function(item){return item.nodeid===_obsWorkspace.nodeid;});}
  var attempts=entry?_obsEntryAttempts(entry):[];
  if(!sameRun||_obsWorkspace.attempt===null||!attempts.some(function(a){return (a.n||1)===_obsWorkspace.attempt;})){
    _obsWorkspace.attempt=attempts.length?(attempts[attempts.length-1].n||attempts.length):null;
  }
  var latestEntries=(manifest.entries||[]).map(_obsLatestAttempt);
  var failed=latestEntries.filter(function(a){return a.outcome==='failed'||a.outcome==='error';}).length;
  var passed=latestEntries.filter(function(a){return a.outcome==='passed';}).length;
  var allEntries=manifest.entries||[];
  var filteredEntries=allEntries.filter(function(item){return _obsEntryMatchesCaseFilter(item,_obsWorkspace.caseFilter);});
  var casePageCount=Math.max(1,Math.ceil(filteredEntries.length/_obsCasePageSize));
  if(!sameRun){
    var selectedIndex=filteredEntries.findIndex(function(item){return item.nodeid===_obsWorkspace.nodeid;});
    _obsWorkspace.casePage=selectedIndex<0?1:Math.floor(selectedIndex/_obsCasePageSize)+1;
  }
  _obsWorkspace.casePage=Math.max(1,Math.min(casePageCount,_obsWorkspace.casePage));
  var pageEntries=filteredEntries.slice((_obsWorkspace.casePage-1)*_obsCasePageSize,_obsWorkspace.casePage*_obsCasePageSize);
  var caseRangeStart=filteredEntries.length?(_obsWorkspace.casePage-1)*_obsCasePageSize+1:0;
  var caseRangeEnd=Math.min(_obsWorkspace.casePage*_obsCasePageSize,filteredEntries.length);
  var totalBytes=0;
  (manifest.entries||[]).forEach(function(item){_obsEntryAttempts(item).forEach(function(a){totalBytes+=Number(a.video&&a.video.bytes||0)+Number(a.syslog&&a.syslog.bytes||0);});});
  var device=(manifest.device_name||(/^ios/.test(manifest.platform||'')?'iOS Device':'Android Emulator'))
    +' · '+[manifest.mode,manifest.udid].filter(Boolean).join(' · ');
  var keepLabel=manifest.keep_policy==='always'?'모든 시도':'실패 시만';
  var cases=pageEntries.map(function(item){
    var itemAttempts=_obsEntryAttempts(item), latest=itemAttempts[itemAttempts.length-1]||{}, status=_obsEntryStatus(item);
    var selected=item.nodeid===_obsWorkspace.nodeid;
    var video=latest.kept&&latest.video, log=latest.kept&&latest.syslog, shot=latest.kept&&latest.screenshot;
    var rowStatusClass=status.key==='fail'?'failed':status.key;
    return '<button type="button" class="obs-run-case is-'+rowStatusClass+(selected?' is-selected':'')+'" data-nodeid="'+esc(item.nodeid||'')+'" onclick="_obsSelectCase(decodeURIComponent(\''+encodeURIComponent(item.nodeid||'')+'\'))">'
      +'<span class="obs-case-dot"></span><span class="obs-case-copy"><span class="obs-case-name">'+esc(_obsShortNode(item.nodeid))+'</span>'
      +'<span class="obs-case-meta"><span>· '+itemAttempts.length+'회 시도</span><span class="obs-case-artifacts">'
      +'<i class="obs-case-artifact '+(video?'on':'')+'">▶</i><i class="obs-case-artifact '+(log?'on':'')+'">▤</i><i class="obs-case-artifact '+(shot?'on':'')+'">▣</i></span></span></span>'
      +'<span class="obs-case-side"><span class="obs-case-duration">'+_obsFormatDuration(latest.duration_sec)+'</span><span class="obs-status '+status.key+'">'+status.label+'</span></span></button>';
  }).join('');
  root.innerHTML='<section class="obs-run-workspace" data-run-id="'+esc(runId)+'" data-platform="'+esc(manifest.platform||'unknown')+'">'
    +'<div class="obs-run-summary">'
    +'<div class="obs-summary-cell"><span class="obs-summary-label">RUN_ID</span><span class="obs-summary-value">'+esc(runId)+'</span></div>'
    +'<div class="obs-summary-cell"><span class="obs-summary-label">기기</span><span class="obs-summary-value">'+esc(device)+'</span></div>'
    +'<div class="obs-summary-cell"><span class="obs-summary-label">결과</span><span class="obs-summary-value obs-summary-result"><b class="pass">'+passed+' 통과</b><b class="fail">'+failed+' 실패</b></span></div>'
    +'<div class="obs-summary-cell"><span class="obs-summary-label">증거 용량</span><span class="obs-summary-value">'+_obsFormatBytes(totalBytes)+'</span></div>'
    +'<div class="obs-summary-cell"><span class="obs-summary-label">보존</span><span class="obs-summary-value">'+keepLabel+'</span></div></div>'
    +'<div class="obs-run-main"><section class="obs-run-list-panel"><div class="obs-panel-head"><strong>TC 결과</strong><span class="obs-panel-count">'+passed+' PASSED</span><span class="obs-panel-hint">실패 TC 클릭 → 증거</span></div>'
    +'<div class="obs-case-filters" role="group" aria-label="TC 결과 필터">'
    +'<button type="button" class="obs-case-filter '+(_obsWorkspace.caseFilter==='all'?'active':'')+'" onclick="_obsSetCaseFilter(\'all\')">전체 '+allEntries.length+'</button>'
    +'<button type="button" class="obs-case-filter '+(_obsWorkspace.caseFilter==='pass'?'active':'')+'" onclick="_obsSetCaseFilter(\'pass\')">성공 '+passed+'</button>'
    +'<button type="button" class="obs-case-filter '+(_obsWorkspace.caseFilter==='fail'?'active':'')+'" onclick="_obsSetCaseFilter(\'fail\')">실패 '+failed+'</button></div>'
    +'<div class="obs-run-cases">'+(cases||'<div class="obs-case-empty">해당하는 TC 결과가 없습니다.</div>')+'</div>'
    +'<div class="obs-case-pager"><span class="obs-case-range">페이지당 '+_obsCasePageSize+'개 · '+caseRangeStart+'–'+caseRangeEnd+' / 전체 '+filteredEntries.length+'개</span><span class="obs-case-pager-nav"><button type="button" onclick="_obsSetCasePage('+(_obsWorkspace.casePage-1)+')" '+(_obsWorkspace.casePage===1?'disabled':'')+'>이전</button><span class="obs-case-page-label">'+_obsWorkspace.casePage+' / '+casePageCount+'</span><button type="button" onclick="_obsSetCasePage('+(_obsWorkspace.casePage+1)+')" '+(_obsWorkspace.casePage===casePageCount?'disabled':'')+'>다음</button></span></div></section>'
    +'<section class="obs-evidence-panel"><div id="obs-evidence-content"></div></section></div></section>';
  _obsPaintEvidence();
}

function _obsSelectCase(nodeid){
  _obsWorkspace.nodeid=nodeid;
  var entry=(_obsWorkspace.manifest.entries||[]).find(function(item){return item.nodeid===nodeid;});
  var attempts=entry?_obsEntryAttempts(entry):[];
  _obsWorkspace.attempt=attempts.length?(attempts[attempts.length-1].n||attempts.length):null;
  _obsWorkspace.tab='video';
  _obsRenderWorkspace(_obsWorkspace.runId,_obsWorkspace.manifest,nodeid);
}

function _obsSelectWorkspaceAttempt(number){
  _obsWorkspace.attempt=number;
  _obsPaintEvidence();
}

var _obsInlineLog={source:'',lines:[],query:'',preset:'all',appId:''};

function _obsInlineLogMatchesPreset(line){
  var preset=_obsInlineLog.preset;
  if(preset==='error') return /(^|\s)E(?:\/|\s)|error|fatal|exception|crash/i.test(line);
  if(preset==='fatal') return /fatal|exception|crash/i.test(line);
  if(preset==='android-runtime') return line.includes('AndroidRuntime');
  if(preset==='app') return !!_obsInlineLog.appId&&line.toLowerCase().includes(_obsInlineLog.appId.toLowerCase());
  return true;
}

function _obsParseLogLine(line){
  var android=String(line||'').match(/^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([^:]+):\s?(.*)$/);
  if(android){
    return {time:android[1],level:android[4],source:android[5].trim()+' ['+android[2]+':'+android[3]+']',message:android[6]};
  }
  var ios=String(line||'').match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+([A-Z][a-z]?)\s+([^\s\[]+)\[(\d+):([^\]]+)\]\s*(.*)$/);
  if(ios){
    return {time:ios[1],level:ios[2],source:ios[3]+' ['+ios[4]+':'+ios[5]+']',message:ios[6]};
  }
  return null;
}

function _obsLogLevelKind(level){
  var code=String(level||'').charAt(0).toUpperCase();
  if(code==='E'||code==='F') return 'error';
  if(code==='W') return 'warning';
  if(code==='I'||code==='N') return 'info';
  if(code==='D'||code==='V') return 'debug';
  return 'other';
}

function _obsHighlightLogText(value,query){
  var source=String(value||''), needle=String(query||'');
  if(!needle) return esc(source);
  var lower=source.toLowerCase(), target=needle.toLowerCase(), html='', start=0, index;
  while((index=lower.indexOf(target,start))!==-1){
    html+=esc(source.slice(start,index))+'<mark>'+esc(source.slice(index,index+needle.length))+'</mark>';
    start=index+needle.length;
  }
  return html+esc(source.slice(start));
}

function _obsFormatLogLine(line,query){
  var parsed=_obsParseLogLine(line);
  if(!parsed){
    return '<div class="obs-log-row raw" data-level="other">'+_obsHighlightLogText(line,query)+'</div>';
  }
  return '<div class="obs-log-row" data-level="'+_obsLogLevelKind(parsed.level)+'">'
    +'<span class="obs-log-time">'+_obsHighlightLogText(parsed.time,query)+'</span>'
    +'<span class="obs-log-level">'+_obsHighlightLogText(parsed.level,query)+'</span>'
    +'<span class="obs-log-source" title="'+esc(parsed.source)+'">'+_obsHighlightLogText(parsed.source,query)+'</span>'
    +'<span class="obs-log-message">'+_obsHighlightLogText(parsed.message,query)+'</span></div>';
}

function _obsRenderInlineLog(){
  var log=document.getElementById('obs-evidence-log');
  if(!log||log.dataset.source!==_obsInlineLog.source) return;
  var query=_obsInlineLog.query.toLowerCase();
  var rows=_obsInlineLog.lines.filter(function(line){
    return _obsInlineLogMatchesPreset(line)&&(!query||line.toLowerCase().includes(query));
  });
  log.innerHTML=rows.length
    ? rows.map(function(line){return _obsFormatLogLine(line,_obsInlineLog.query);}).join('')
    : '<div class="obs-log-empty">일치하는 로그가 없습니다.</div>';
  var count=document.getElementById('obs-log-count');
  if(count) count.textContent=rows.length+' / '+_obsInlineLog.lines.length+'줄 표시';
  document.querySelectorAll('.obs-log-filter').forEach(function(button){
    button.classList.toggle('active',button.dataset.preset===_obsInlineLog.preset);
  });
}

function _obsFilterInlineLog(value){
  _obsInlineLog.query=String(value||'');
  _obsRenderInlineLog();
}

function _obsSetInlineLogPreset(preset){
  _obsInlineLog.preset=preset;
  _obsRenderInlineLog();
}

function _obsPaintEvidence(){
  var host=document.getElementById('obs-evidence-content');
  var manifest=_obsWorkspace.manifest||{}, runId=_obsWorkspace.runId, nodeid=_obsWorkspace.nodeid;
  if(!host||!nodeid) return;
  var entry=(manifest.entries||[]).find(function(item){return item.nodeid===nodeid;})||{};
  var attempts=_obsEntryAttempts(entry);
  var attempt=attempts.find(function(a){return (a.n||1)===_obsWorkspace.attempt;})||attempts[attempts.length-1]||{};
  var status=_obsEntryStatus(entry), hasVideo=attempt.kept&&attempt.video, hasLog=attempt.kept&&attempt.syslog, hasShot=attempt.kept&&attempt.screenshot;
  var attemptButtons=attempts.map(function(item){var n=item.n||1;return '<button type="button" class="obs-attempt '+(n===_obsWorkspace.attempt?'active':'')+'" data-obs-attempt="'+n+'" onclick="_obsSelectWorkspaceAttempt('+n+')">'+n+'</button>';}).join('');
  host.innerHTML='<div class="obs-evidence-head"><span class="obs-status '+status.key+'">'+status.label+'</span><span class="obs-evidence-title">'+esc(_obsShortNode(nodeid))+'</span></div>'
    +'<div class="obs-evidence-toolbar"><span class="obs-attempts">시도 '+attemptButtons+'</span></div><div class="obs-evidence-body" id="obs-workspace-body"></div>';
  var body=document.getElementById('obs-workspace-body');
  var videoBody='';
  if(hasVideo){
    var offset=Number(attempt.failure_offset_sec)||0;
    var mins=Math.floor(offset/60), secs=(offset%60).toFixed(1).padStart(4,'0');
    var label=(mins<10?'0':'')+mins+':'+secs+' CRASH';
    var crashMarker=status.key==='fail'?'<span class="obs-crash-marker">● '+label+'</span>':'';
    videoBody='<div class="obs-video-shell"><div class="obs-video-frame"><span class="obs-video-caption">실제 실행 녹화</span>'+crashMarker
      +'<video class="obs-evidence-video" controls preload="metadata" src="'+esc(_obsAttemptUrl('video',runId,nodeid,attempt))+'"></video></div>'
      +'<div class="obs-video-meta"><span>'+_obsFormatBytes(attempt.video.bytes)+'</span><span>'+_obsFormatDuration(attempt.duration_sec)+'</span><span>'+attempts.length+'회 시도</span><span>'+(attempt===(attempts[attempts.length-1])?'마지막 attempt':'attempt '+(attempt.n||1))+'</span></div></div>';
  }else{
    videoBody='<div class="obs-evidence-empty">'+esc(_evEvidenceReason(attempt,'video'))+'</div>';
  }
  var logBody='';
  var logUrl=hasLog?_obsAttemptUrl('log',runId,nodeid,attempt):'';
  if(hasLog){
    var appPreset=manifest.app_id?'<button type="button" class="obs-log-filter" data-preset="app" onclick="_obsSetInlineLogPreset(\'app\')">앱 로그</button>':'';
    logBody='<div class="obs-log-toolbar"><input class="obs-log-search" type="search" placeholder="로그 검색" oninput="_obsFilterInlineLog(this.value)">'
      +'<button type="button" class="obs-log-filter active" data-preset="all" onclick="_obsSetInlineLogPreset(\'all\')">전체</button>'
      +'<button type="button" class="obs-log-filter" data-preset="error" onclick="_obsSetInlineLogPreset(\'error\')">오류</button>'
      +'<button type="button" class="obs-log-filter" data-preset="fatal" onclick="_obsSetInlineLogPreset(\'fatal\')">치명적</button>'
      +'<button type="button" class="obs-log-filter" data-preset="android-runtime" onclick="_obsSetInlineLogPreset(\'android-runtime\')">AndroidRuntime</button>'+appPreset+'</div>'
      +'<div class="obs-evidence-log" id="obs-evidence-log" data-source="'+esc(logUrl)+'"><div class="obs-log-empty">로그를 불러오는 중...</div></div><div class="obs-log-count" id="obs-log-count"></div>';
  }else{
    logBody='<div class="obs-evidence-empty">'+esc(_evEvidenceReason(attempt,'log'))+'</div>';
  }
  var shotBody='';
  if(hasShot){
    var shotUrl=attempt.screenshot_url||('/screenshots/'+String(attempt.screenshot.path||'').replace(/^reports\/screenshots\//,''));
    shotBody='<img class="obs-evidence-shot" src="'+esc(shotUrl)+'" alt="실행 스크린샷">';
  }else{
    shotBody='<div class="obs-evidence-empty">스크린샷이 없습니다.</div>';
  }
  var platform=String(manifest.platform||'');
  var tcFile=(function(nid,plat){
    var prefix='tests/generated/'+plat+'/';
    if(!nid.startsWith(prefix)) return '';
    return nid.slice(prefix.length).split('::')[0];
  })(nodeid,platform);
  var tcSectionId='obs-tc-content-'+Date.now();
  var tcBody='<div class="obs-evidence-empty obs-tc-loading" id="'+tcSectionId+'">TC 정보를 불러오는 중...</div>';
  body.innerHTML='<section class="obs-evidence-section" data-kind="video"><div class="obs-evidence-section-head">▶ 영상</div><div class="obs-evidence-section-body">'+videoBody+'</div></section>'
    +'<section class="obs-evidence-section" data-kind="log"><div class="obs-evidence-section-head">▤ 시스템 로그</div><div class="obs-evidence-section-body">'+logBody+'</div></section>'
    +'<section class="obs-evidence-section" data-kind="shot"><div class="obs-evidence-section-head">▣ 스크린샷</div><div class="obs-evidence-section-body">'+shotBody+'</div></section>'
    +(tcFile?'<section class="obs-evidence-section" data-kind="tc"><div class="obs-evidence-section-head">📋 TC 내용</div><div class="obs-evidence-section-body">'+tcBody+'</div></section>':'');
  if(tcFile){
    fetch('/api/testcase?platform='+encodeURIComponent(platform)+'&file='+encodeURIComponent(tcFile))
      .then(function(r){return r.json();})
      .then(function(data){
        var el=document.getElementById(tcSectionId);
        if(!el) return;
        el.className='';
        if(data.ok){
          el.textContent=data.content;
          el.style.cssText='white-space:pre-wrap;font:10px/1.65 monospace;padding:10px;color:var(--text2);max-height:320px;overflow-y:auto;';
        } else {
          el.textContent=data.error||'TC 파일을 찾을 수 없습니다.';
          el.style.cssText='padding:10px;color:var(--text3);font-size:11px;';
        }
      })
      .catch(function(){ var el=document.getElementById(tcSectionId); if(el){el.textContent='TC 파일 로드 실패';el.style.cssText='padding:10px;color:var(--text3);font-size:11px;';} });
  }
  if(hasVideo){
    var video=body.querySelector('.obs-evidence-video');
    if(video&&status.key==='fail') video.addEventListener('loadedmetadata',function(){
      var end=Number.isFinite(video.duration)?Math.max(0,video.duration-.1):offset;
      var target=Math.min(offset,end);
      video.currentTime=target;
      var marker=body.querySelector('.obs-crash-marker');
      if(marker){
        var targetMins=Math.floor(target/60), targetSecs=(target%60).toFixed(1).padStart(4,'0');
        marker.textContent='● '+(targetMins<10?'0':'')+targetMins+':'+targetSecs+' CRASH';
      }
    },{once:true});
  }
  _obsInlineLog={source:logUrl,lines:[],query:'',preset:'all',appId:String(manifest.app_id||'')};
  if(hasLog){
    fetch(logUrl).then(function(response){if(!response.ok) throw new Error('log');return response.text();}).then(function(text){
      var log=document.getElementById('obs-evidence-log');
      if(!log||log.dataset.source!==logUrl) return;
      _obsInlineLog.lines=text.split('\n');
      var input=document.querySelector('.obs-log-search');
      _obsInlineLog.query=input?input.value:'';
      _obsRenderInlineLog();
    }).catch(function(){
      var log=document.getElementById('obs-evidence-log');
      if(log&&log.dataset.source===logUrl) log.textContent='로그를 불러오지 못했습니다.';
    });
  }
}

// ── 빠른 실행 TC 결과에 증거 버튼 주입 ─────────────────────
// 실행 완료 후 run_id와 manifest를 받아 TC 행에 증거 도트+버튼 추가
async function _obsResolveLatestRunId(platform){
  var selected=platform==='ios'?'ios':'android';
  var prefix='run_'+selected+'_';
  var runId='';
  // Server state is authoritative. WebSocket start/summary messages can be
  // missed while the browser reconnects, and cached IDs can point at an older run.
  try{
    var statusRes=await fetch('/api/status?platform='+encodeURIComponent(selected));
    if(statusRes.ok){
      var status=await statusRes.json();
      var statusRunId=String(status.obs_last_run_id||'').trim();
      if(statusRunId.indexOf(prefix)===0) runId=statusRunId;
    }
  }catch(_){}
  if(!runId){
    try{
      var runsRes=await fetch('/api/run_artifacts?platform='+encodeURIComponent(selected)+'&limit=1');
      if(runsRes.ok){
        var runsData=await runsRes.json();
        var listed=String((runsData.runs&&runsData.runs[0]&&runsData.runs[0].run_id)||'').trim();
        if(listed.indexOf(prefix)===0) runId=listed;
      }
    }catch(_){}
  }
  if(!runId&&String(_obsLastRunId||'').indexOf(prefix)===0) runId=String(_obsLastRunId);
  if(!runId){
    try{
      var cached=localStorage.getItem('qa-native-app.obs-last-run-id.'+selected)||'';
      if(cached.indexOf(prefix)===0) runId=cached;
    }catch(_){}
  }
  if(runId){
    _obsLastRunId=runId;
    try{localStorage.setItem('qa-native-app.obs-last-run-id.'+selected,runId);}catch(_){}
  }
  return runId;
}

async function _obsRenderCompletedQuickRun(platform){
  var root=document.getElementById('quick-generated-result');
  var runId=await _obsResolveLatestRunId(platform);
  if(!runId){
    if(root) root.innerHTML='<section class="obs-run-workspace obs-workspace-error"><div class="obs-evidence-empty">실행 아티팩트를 찾지 못했습니다. 잠시 후 다시 확인하세요.</div></section>';
    return false;
  }
  try{history.replaceState(null,'','#obs/'+encodeURIComponent(runId));}catch(_){}
  await _obsInjectEvidenceButtons(runId);
  return !!document.querySelector('.obs-run-workspace[data-run-id="'+runId+'"]');
}

async function _obsInjectEvidenceButtons(runId){
  if(!runId) return;
  var pinnedHash=window.location.hash||'';
  if(pinnedHash.indexOf('#obs/')===0){
    try{
      var pinnedRunId=decodeURIComponent(pinnedHash.slice(5));
      if(pinnedRunId&&pinnedRunId!==runId) return;
      var activeWorkspace=document.querySelector('.obs-run-workspace');
      if(pinnedRunId===runId&&activeWorkspace&&activeWorkspace.dataset.runId===runId) return;
    }catch(_){ return; }
  }
  try{
    var res=await fetch('/api/run_artifacts/'+encodeURIComponent(runId));
    if(!res.ok) return;
    var manifest=await res.json();
    _obsRenderWorkspace(runId,manifest);
  }catch(_){}
}

async function _obsOpenHash(){
  var hash=window.location.hash||'';
  if(hash.indexOf('#obs/')!==0) return;
  var runId='';
  try{ runId=decodeURIComponent(hash.slice(5)); }catch(_){ return; }
  if(!/^run_[a-z]+_\d{8}_\d{6}_\d{3}$/.test(runId)) return;
  try{
    var res=await fetch('/api/run_artifacts/'+encodeURIComponent(runId));
    if(!res.ok) return;
    var manifest=await res.json();
    var entries=manifest.entries||[];
    var entry=entries.find(function(e){
      var attempts=(e.attempts&&e.attempts.length)?e.attempts:[e];
      var latest=attempts[attempts.length-1]||{};
      return (latest.outcome==='failed'||latest.outcome==='error')
        &&latest.kept&&(latest.video||latest.syslog||latest.screenshot);
    })||entries.find(function(e){
      var attempts=(e.attempts&&e.attempts.length)?e.attempts:[e];
      var latest=attempts[attempts.length-1]||{};
      return latest.kept&&(latest.video||latest.syslog||latest.screenshot);
    });
    if(!entry) return;
    var nav=document.querySelector('.sidebar-item[data-view="tests"]');
    if(nav) selectView('tests',nav);
    _obsRenderWorkspace(runId,manifest,entry.nodeid);
  }catch(_){}
}

window.addEventListener('hashchange',_obsOpenHash);
