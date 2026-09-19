// ── 초기화 ───────────────────────────────────────────────────
(async function init(){
  initReportControls();
  renderRunHistory();
  renderProgressBar();
  updateStepLocks();
  refreshOverview();
  await Promise.all([refreshStatus(),refreshGenerated(),refreshReports(),refreshTcFolders(),refreshImportFiles()]);
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
  setInterval(refreshImportFiles, 15000);
  pollEnvStatus();
  setInterval(pollEnvStatus, 3000);
})();
