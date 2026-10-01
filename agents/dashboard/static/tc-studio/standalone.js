window.TCS.init('#tc-studio-root').catch(function (error) {
  document.getElementById('tc-studio-root').textContent = 'TC Studio를 불러오지 못했습니다: ' + error.message;
});

async function refreshStudioStatus() {
  try {
    const [statusResponse, stateResponse] = await Promise.all([
      fetch('/api/status'), fetch('/api/state')
    ]);
    if (!statusResponse.ok || !stateResponse.ok) return;
    const status = await statusResponse.json();
    const state = await stateResponse.json();
    const appiumDot = document.getElementById('dot-appium');
    const deviceDot = document.getElementById('dot-device');
    appiumDot.className = 'status-dot ' + (status.appium ? 'on' : 'off');
    deviceDot.className = 'status-dot ' + (status.device_count > 0 ? 'on' : 'off');
    document.getElementById('txt-appium').textContent = status.appium ? 'Appium 연결됨' : 'Appium 미기동';
    document.getElementById('txt-device').textContent = status.device_count > 0
      ? status.devices.join(', ') : '디바이스 없음';
    document.getElementById('txt-automation').textContent = status.platform === 'ios'
      ? '자동화: XCUITest' : '자동화: ADB';
    document.getElementById('txt-step').textContent = state.step || 'init';
    const healCount = Number(state.heal_count || 0);
    document.getElementById('heal-row').hidden = healCount === 0;
    document.getElementById('heal-cnt').textContent = healCount;
  } catch (_) { /* 다음 갱신에서 복구 */ }
}
refreshStudioStatus();
setInterval(refreshStudioStatus, 15000);
