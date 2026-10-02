// ── 초기화 ───────────────────────────────────────────────────
(async function init(){
  var initialParams=new URLSearchParams(location.search);
  var initialView=location.pathname === '/tc-studio' ? 'tc_studio' : initialParams.get('view');
  var initialPlatform=initialParams.get('platform');
  if(['android','ios'].includes(initialPlatform)){
    var platformRadio=document.querySelector('input[name="platform"][value="'+initialPlatform+'"]');
    if(platformRadio){
      platformRadio.checked=true;
      _initialPlatformSync=false;
      updateAutomationStatus(initialPlatform);
    }
  }
  if(['dashboard','config','capture','pipeline','tests','reports','history','tc_studio'].includes(initialView)){
    selectView(initialView, document.querySelector('.sidebar-item[data-view="'+initialView+'"]'), {preserveRun:location.hash.indexOf('#obs/')===0});
  }
  initReportControls();
  renderRunHistory();
  renderProgressBar();
  updateStepLocks();
  refreshOverview();
  await Promise.all([refreshStatus(),refreshGenerated(),refreshReports(),refreshTcFolders()]);
  loadDevicePicker(getPlatform(), 'pipeline');
  // 관측성 스트립 초기 렌더
  _obsRenderStrips();
  // 페이지 로드 시 마지막 run_id로 아티팩트 도트 복원
  try{
    var _pst=await fetch('/api/status');
    if(_pst.ok){
      var _pstd=await _pst.json();
      var _lastRid=(_pstd.obs_last_run_id||'').trim();
      if(_lastRid) setTimeout(function(){ _obsInjectEvidenceButtons(_lastRid); }, 600);
    }
  }catch(_){}
  await _obsOpenHash();
  // 플랫폼 라디오 변경 시 파이프라인 디바이스 피커 갱신
  document.querySelectorAll('input[name="platform"]').forEach(function(r){
    r.addEventListener('change', function(){ loadDevicePicker(getPlatform(), 'pipeline'); });
  });
  setInterval(refreshOverview, 2000);
  setInterval(refreshStatus, 6000);
  setInterval(refreshGenerated, 10000);
  setInterval(refreshReports, 15000);
  setInterval(refreshTcFolders, 15000);
  pollEnvStatus();
  setInterval(pollEnvStatus, 3000);
})();
