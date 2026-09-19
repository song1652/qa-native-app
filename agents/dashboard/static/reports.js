var _reports=[], _reportSelected=new Set(), _reportPage=1, _reportSort='newest', _reportSearch='';
function renderReports(){
  var list=document.getElementById('report-list'); if(!list) return;
  var filtered=_reports.filter(function(r){return r.name.toLowerCase().includes(_reportSearch.toLowerCase());}).sort(function(a,b){
    if(_reportSort==='name') return a.name.localeCompare(b.name);
    var d=new Date(b.modified_at)-new Date(a.modified_at); return _reportSort==='oldest'?-d:d;
  });
  var pages=Math.max(1,Math.ceil(filtered.length/8)); _reportPage=Math.min(_reportPage,pages);
  var pageItems=filtered.slice((_reportPage-1)*8,_reportPage*8);
  list.innerHTML=pageItems.map(function(r){return '<div class="report-item" data-name="'+esc(r.name)+'" tabindex="0" onclick="openReportFromRow(event,this)" onkeydown="openReportFromRow(event,this)"><input type="checkbox" '+(_reportSelected.has(r.name)?'checked':'')+' onchange="toggleReportSelection(this.dataset.name,this.checked);showReport(this.dataset.name)" data-name="'+esc(r.name)+'"><div class="report-info"><div class="report-name" title="'+esc(r.name)+'">'+esc(r.name)+'</div><div class="report-meta">'+new Date(r.modified_at).toLocaleString('ko-KR')+' · '+Math.round(r.size/1024)+' KB</div></div><div class="report-actions"><button onclick="showReport(this.closest(\'.report-item\').dataset.name)">열기</button><a href="/reports/'+encodeURIComponent(r.name)+'" target="_blank">새 탭</a><button class="report-danger" onclick="deleteReports([this.closest(\'.report-item\').dataset.name])">삭제</button></div></div>';}).join('')||'<div class="report-empty">검색 결과가 없습니다.</div>';
  document.getElementById('report-count').textContent=filtered.length+'개 리포트';
  document.getElementById('report-selection-count').textContent=_reportSelected.size+'개 선택';
  document.getElementById('report-page').textContent=_reportPage+' / '+pages;
  document.getElementById('report-prev').disabled=_reportPage<=1; document.getElementById('report-next').disabled=_reportPage>=pages;
  var all=document.getElementById('report-select-all'); all.checked=!!filtered.length && filtered.every(function(r){return _reportSelected.has(r.name);}); all.indeterminate=filtered.some(function(r){return _reportSelected.has(r.name);})&&!all.checked;
}
async function refreshReports(){try{var res=await fetch('/api/reports');_reports=await res.json();renderReports();}catch(_){} }
function toggleReportSelection(name,checked){if(checked)_reportSelected.add(name);else _reportSelected.delete(name);renderReports();}
function openReportFromRow(event,row){
  if(!row) return;
  if(event.type==='click' && event.target.closest('input,button,a')) return;
  if(event.type==='keydown'){
    if(event.key!=='Enter' && event.key!==' ') return;
    event.preventDefault();
  }
  showReport(row.dataset.name);
}
function showReport(name){var frame=document.getElementById('report-iframe'),wrap=document.getElementById('report-iframe-wrap'),empty=document.getElementById('report-preview-empty'),title=document.getElementById('report-preview-title'),close=document.getElementById('report-close');if(!frame||!wrap)return;frame.src='/reports/'+encodeURIComponent(name);wrap.style.display='block';empty.style.display='none';title.textContent=name;close.style.display='block';document.querySelectorAll('.report-item').forEach(function(r){r.classList.toggle('is-open',r.dataset.name===name);});}
function closeReport(){var frame=document.getElementById('report-iframe'),wrap=document.getElementById('report-iframe-wrap'),empty=document.getElementById('report-preview-empty'),title=document.getElementById('report-preview-title'),close=document.getElementById('report-close');if(frame)frame.src='';if(wrap)wrap.style.display='none';if(empty)empty.style.display='flex';if(title)title.textContent='미리보기';if(close)close.style.display='none';}
function reportConfirmDelete(names){
  return new Promise(function(resolve){
    var dialog=document.createElement('dialog'); dialog.className='report-delete-dialog';
    dialog.innerHTML='<form method="dialog"><h2>리포트 삭제</h2><p>'+(names.length===1?esc(names[0]):names.length+'개 리포트')+'를 삭제하시겠습니까?<br>삭제한 리포트는 복구할 수 없습니다.</p><div class="report-dialog-actions"><button value="cancel" autofocus>취소</button><button value="delete" class="report-danger">삭제</button></div></form>';
    dialog.addEventListener('close',function(){var ok=dialog.returnValue==='delete';dialog.remove();resolve(ok);},{once:true});
    document.body.appendChild(dialog); dialog.showModal();
  });
}
async function deleteReports(names){if(!names.length||!(await reportConfirmDelete(names)))return;try{var res=await fetch('/api/reports/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({names:names})});var data=await res.json();if(!res.ok||!data.ok)throw new Error(data.error||'삭제 실패');names.forEach(function(n){_reportSelected.delete(n);});refreshReports();closeReport();}catch(e){alert(e.message);}}
function initReportControls(){
  var search=document.getElementById('report-search-input'), sort=document.getElementById('report-sort');
  if(search) search.oninput=function(){_reportSearch=this.value;_reportPage=1;renderReports();};
  if(sort) sort.onchange=function(){_reportSort=this.value;_reportPage=1;renderReports();};
  document.getElementById('report-refresh').onclick=function(){refreshReports();};
  document.getElementById('report-delete-selected').onclick=function(){deleteReports(Array.from(_reportSelected));};
  document.getElementById('report-select-all').onchange=function(){var q=_reports.filter(function(r){return r.name.toLowerCase().includes(_reportSearch.toLowerCase());});q.forEach(function(r){this.checked?_reportSelected.add(r.name):_reportSelected.delete(r.name);},this);renderReports();};
  document.getElementById('report-prev').onclick=function(){_reportPage--;renderReports();};document.getElementById('report-next').onclick=function(){_reportPage++;renderReports();};
}
