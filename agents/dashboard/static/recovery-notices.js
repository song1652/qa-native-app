// Reads only: actions remain explicit links and acknowledgments stay in this browser.
var _recoveryNotices = {items: [], seen: new Set(), busy: false, disconnected: false};
var _recoveryAckKey = 'qa-native-app.recovery-acknowledged';
var _recoveryAcknowledged = [];
try {
  var savedAcknowledgments = JSON.parse(localStorage.getItem(_recoveryAckKey) || '[]');
  if(Array.isArray(savedAcknowledgments)) _recoveryAcknowledged = savedAcknowledgments.filter(function(id){ return typeof id === 'string'; }).slice(-100);
} catch(error) { /* Browser storage may be unavailable; acknowledgment still works in memory. */ }

async function safeNoticeGet(url, options) {
  if(url !== '/api/recovery-notices' || (options && options.method && options.method !== 'GET')) throw new Error('허용되지 않은 알림 읽기 요청');
  for(var attempt = 0; attempt < 3; attempt++) {
    var controller = new AbortController();
    var timer = setTimeout(function(){ controller.abort(); }, 5000);
    var retry = false;
    try {
      var response = await fetch(url, {method: 'GET', signal: controller.signal, cache: 'no-store'});
      if(response.ok) return await response.json();
      retry = [502, 503, 504].includes(response.status);
      if(!retry || attempt === 2) throw new Error('알림을 읽을 수 없습니다.');
    } catch(error) {
      if(!retry && !(error instanceof TypeError) && error.name !== 'AbortError') throw error;
      if(attempt === 2) throw error;
    } finally { clearTimeout(timer); }
    await new Promise(function(resolve){ setTimeout(resolve, attempt === 0 ? 500 : 1000); });
  }
}

function recoveryNoticesRender() {
  var details = document.getElementById('recovery-notices');
  if(!details) return;
  var visible = _recoveryNotices.items.filter(function(item){ return !_recoveryAcknowledged.includes(item.id); });
  details.hidden = visible.length === 0;
  details.querySelector('summary').textContent = '알림 ' + visible.length;
  var list = document.getElementById('recovery-notice-list');
  var rendered = JSON.stringify(visible);
  if(_recoveryNotices.rendered === rendered) return;
  _recoveryNotices.rendered = rendered;
  var focused = list.contains(document.activeElement) ? document.activeElement : null;
  var focusedId = focused && focused.closest('li').dataset.noticeId;
  var focusedTag = focused && focused.tagName;
  list.replaceChildren();
  visible.forEach(function(item){
    var row = document.createElement('li');
    row.className = 'recovery-notice';
    row.dataset.noticeId = item.id;
    var title = document.createElement('strong');
    title.textContent = item.title || '확인이 필요한 알림';
    var context = document.createElement('small');
    context.className = 'recovery-notice-context';
    var platform = item.platform === 'android' ? 'Android' : item.platform === 'ios' ? 'iOS' : '';
    var groups = Array.isArray(item.groups) ? item.groups.filter(function(group){ return typeof group === 'string' && group.trim(); }) : [];
    context.textContent = [platform, groups.join(', ')].filter(Boolean).join(' · ');
    var date = typeof item.created_at === 'string' ? new Date(item.created_at) : null;
    if(date && Number.isFinite(date.getTime())) {
      if(context.textContent) context.appendChild(document.createTextNode(' · '));
      var time = document.createElement('time');
      time.dateTime = item.created_at;
      time.textContent = date.toLocaleString('ko-KR', {year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'});
      context.appendChild(time);
    }
    var message = document.createElement('p');
    message.textContent = item.message || '';
    var actions = document.createElement('div');
    actions.className = 'recovery-notice-actions';
    // Only same-origin relative destinations are allowed, even for malformed responses.
    if(typeof item.href === 'string' && /^\/(?!\/)/.test(item.href) && !/[\\\s]/.test(item.href)) {
      var link = document.createElement('a');
      link.href = item.href;
      link.textContent = item.action_label || '확인하기';
      actions.appendChild(link);
    }
    var acknowledge = document.createElement('button');
    acknowledge.type = 'button';
    acknowledge.textContent = '확인했어요';
    acknowledge.addEventListener('click', function(){
      _recoveryAcknowledged = _recoveryAcknowledged.filter(function(id){ return id !== item.id; }).concat(item.id).slice(-100);
      try { localStorage.setItem(_recoveryAckKey, JSON.stringify(_recoveryAcknowledged)); } catch(error) { /* In-memory acknowledgment remains available. */ }
      recoveryNoticesRender();
      // Keep keyboard focus on the remaining notices, or the brand if all are acknowledged.
      (details.hidden ? document.querySelector('.product-brand') : details.querySelector('summary')).focus();
    });
    actions.appendChild(acknowledge);
    row.appendChild(title);
    if(context.textContent) row.appendChild(context);
    row.append(message, actions);
    list.appendChild(row);
  });
  if(focusedId) {
    var focusedRow = Array.from(list.children).find(function(row){ return row.dataset.noticeId === focusedId; });
    var control = focusedRow && focusedRow.querySelector(focusedTag);
    if(control) control.focus({preventScroll: true});
  }
}

async function recoveryNoticesRefresh() {
  if(_recoveryNotices.busy || !document.getElementById('recovery-notices')) return;
  _recoveryNotices.busy = true;
  var announcement = document.getElementById('recovery-announcement');
  var warning = document.getElementById('recovery-connection-warning');
  try {
    var data = await safeNoticeGet('/api/recovery-notices');
    if(!data || data.ok !== true || !Array.isArray(data.notices)) throw new Error('알림 응답 오류');
    var ids = new Set();
    _recoveryNotices.items = data.notices.filter(function(item){
      if(!item || typeof item.id !== 'string' || ids.has(item.id)) return false;
      ids.add(item.id); return true;
    }).slice(0, 100);
    var fresh = _recoveryNotices.items.filter(function(item){ return !_recoveryNotices.seen.has(item.id) && !_recoveryAcknowledged.includes(item.id); });
    _recoveryNotices.items.forEach(function(item){ _recoveryNotices.seen.add(item.id); });
    if(_recoveryNotices.disconnected) announcement.textContent = '서버 연결이 복구되었습니다.';
    else if(fresh.length) announcement.textContent = '새 알림 ' + fresh.length + '개가 있습니다.';
    _recoveryNotices.disconnected = false;
    warning.hidden = true;
  } catch(error) {
    if(!_recoveryNotices.disconnected) announcement.textContent = '서버 연결을 확인하세요. 기존 알림은 유지됩니다.';
    _recoveryNotices.disconnected = true;
    warning.hidden = false;
  } finally {
    recoveryNoticesRender();
    _recoveryNotices.busy = false;
  }
}

if(document.getElementById('recovery-notices')) {
  recoveryNoticesRefresh();
  setInterval(recoveryNoticesRefresh, 6000);
}
