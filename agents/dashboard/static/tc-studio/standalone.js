window.TCS.init('#tc-studio-root').catch(function (error) {
  document.getElementById('tc-studio-root').textContent = 'TC 스튜디오를 불러오지 못했습니다: ' + error.message;
});
