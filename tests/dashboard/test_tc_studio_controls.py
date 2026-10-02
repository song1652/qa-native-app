"""TC controls are checked with temporary storage and mocked external services."""
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect
from tests.dashboard.test_tc_studio_e2e import tc_server  # noqa: F401
from tests.unit.tc_library.test_tc_platform_results import _workbook

STATIC = Path(__file__).resolve().parents[2] / 'agents/dashboard/static/tc-studio'


def studio(page, url):
    page.set_default_timeout(3000)
    def route_api(route):
        path = urlparse(route.request.url).path
        if path == '/api/tc-library/credentials':
            route.fulfill(json={'confluence': {'configured':False}, 'figma':{'configured':False}})
        elif path.startswith('/api/tc-library'):
            route.continue_()
        else:
            route.fulfill(json={'ok':True, 'appium':False, 'devices':[], 'suites':[], 'folders':[], 'state':{}})
    page.route('**/api/**', route_api)
    page.route('**/capture/**', lambda route: route.fulfill(json={'ok':True, 'active':False}))
    page.goto(url + '/tc-studio')
    expect(page.locator('#screen-generate')).to_have_class('screen active')


def test_excel_history_note_edit_requires_a_fresh_checked_export(page):
    page.set_content('<div id="root" class="tc-studio"></div>')
    page.add_script_tag(path=str(STATIC / 'state.js'))
    page.evaluate('''() => {
        Object.assign(TCS_NS.state, {suite:'demo', suites:[{suite:'demo',count:1,sheets:['Sheet']}], tree:[]});
        TCS_NS.api={mdEligibility:async()=>({funnel:[{label:'all',count:0}],branches:[],drifted:[],excluded:[]}),
            exportXlsx:async(s,p)=>({checks:[{level:'ok',message:'checked'}],filename:'demo.xlsx',count:1,export_id:'export-1'})};
    }''')
    page.add_script_tag(path=str(STATIC / 'export.js'))
    page.evaluate('''() => {const r=document.getElementById('root'); r.innerHTML=TCS_NS.exportView.html(); TCS_NS.exportView.mount(r); TCS_NS.exportView.onShow();}''')
    page.locator('#xlsx-run-check').click()
    expect(page.locator('#xlsx-download')).to_be_enabled()
    page.locator('#xlsx-history-note').fill('New history entry')
    expect(page.locator('#xlsx-download')).to_be_disabled()
    expect(page.locator('#xlsx-checks')).to_contain_text('검사를 다시')


def test_excel_modal_escape_closes_and_restores_opener(page, tc_server):
    studio(page, tc_server)
    opener = page.locator('#btn-import-xlsx')
    opener.click()
    expect(page.locator('#import-modal')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#import-modal')).to_be_hidden()
    expect(opener).to_be_focused()


def test_excel_import_mapping_filter_and_history_rollback(page, tc_server, tmp_path):
    studio(page, tc_server)
    page.locator('#btn-import-xlsx').click()
    page.locator('#import-mapping-mode').select_option('custom')
    for field, value in {'feature':'B','steps':'C','expected':'D','l1':'A'}.items():
        page.locator(f'[data-map="{field}"]').fill(value)
    page.locator('#import-profile-name').fill('Audit mapping')
    page.locator('[data-id="import-profile-save"]').click()
    expect(page.locator('#import-mapping-profile')).not_to_have_value('')
    page.locator('#import-profile-name').fill('Updated mapping')
    page.locator('[data-id="import-profile-update"]').click()
    expect(page.locator('#import-mapping-profile option:checked')).to_have_text('Updated mapping')
    page.locator('[data-id="import-profile-delete"]').click()
    expect(page.locator('#import-mapping-profile')).to_have_value('')
    page.locator('#import-mapping-mode').select_option('auto')
    source = _workbook(tmp_path/'audit.xlsx', True)
    page.locator('#import-file').set_input_files(str(source))
    expect(page.locator('#import-preview')).to_be_visible()
    page.locator('#import-suite').fill('controls')
    page.locator('#import-plan').click()
    expect(page.locator('#import-plan-panel')).to_be_visible()
    page.locator('#import-confirm').click()
    expect(page.locator('#suite-select')).to_have_value('controls')
    page.locator('[data-id="nav-tab-library"]').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(2)
    page.locator('#lib-filter-mismatch').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(1)
    page.locator('#lib-filter-reset').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(2)
    page.locator('#grid-check-all').check()
    expect(page.locator('#bulk-n')).to_have_text('2')
    page.locator('#bulk-clear').click()
    expect(page.locator('#bulkbar')).to_be_hidden()
    page.locator('#btn-import-xlsx').click()
    page.locator('#import-history-open').click()
    page.locator('[data-action="view"]').first.click()
    page.locator('[data-action="rollback"]').click()
    expect(page.locator('#import-history-detail')).to_contain_text('rolled_back')


def test_library_create_edit_duplicate_delete_undo_and_platform_filters(page, tc_server):
    studio(page, tc_server)
    page.locator('[data-id="nav-tab-library"]').click()
    page.locator('#btn-add-case').click()
    expect(page.locator('#detail')).to_be_visible()
    page.locator('#detail-feature').fill('Control audit case')
    page.locator('#detail-precondition').fill('앱이 열려 있다')
    page.locator('#detail-step-add').click()
    page.locator('[data-id="detail-step-input"]').fill('버튼을 누른다')
    page.locator('#detail-expected').fill('결과 화면이 표시된다')
    page.locator('#detail-tags').fill('audit, smoke, audit')
    page.locator('#detail-priority').select_option('P1')
    page.locator('#detail-result-android').select_option('pass')
    page.locator('#detail-result-ios').select_option('fail')
    page.locator('#detail-save').click()
    expect(page.locator('#detail-save')).to_be_disabled()
    expect(page.locator('#detail-tags')).to_have_value('audit, smoke')
    page.locator('#detail-duplicate').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(2)
    page.locator('#detail-delete').click()
    page.locator('#cf-ok').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(1)
    page.locator('[data-id="delete-undo"]').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(2)
    page.locator('#lib-filter-mismatch').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(2)
    page.locator('#lib-filter-reset').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(2)
    page.locator('#tree-toggle').click()
    expect(page.locator('#lib')).to_have_class('lib no-detail tree-hidden')
    page.keyboard.press('/')
    expect(page.locator('#lib-search')).to_be_focused()
    page.locator('#lib-search').fill('does-not-exist')
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(0)
    page.locator('#lib-filter-reset').click()
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(2)


def test_suite_delete_restore_and_permanent_delete_confirmation(page, tc_server):
    import _tc_library as lib
    from _tc_model import new_case
    lib.import_cases('trash-audit', ['Sheet'], [new_case(case_id='AUD_0001',sheet='Sheet',path=['Audit','',''],feature='Audit')], 'seed')
    studio(page, tc_server)
    page.locator('#suite-select').select_option('trash-audit')
    page.locator('#suite-menu-btn').click()
    page.locator('#suite-menu-delete').click()
    expect(page.locator('#sd-summary')).to_contain_text('1')
    page.locator('#sd-ok').click()
    expect(page.locator('#suite-delete-modal')).to_be_hidden()
    page.locator('#suite-menu-btn').click()
    page.locator('#suite-menu-trash').click()
    page.locator('[data-id="trash-restore"]').click()
    expect(page.locator('#suite-select')).to_have_value('trash-audit')
    page.locator('#suite-menu-btn').click()
    page.locator('#suite-menu-delete').click()
    page.locator('#sd-ok').click()
    expect(page.locator('#suite-delete-modal')).to_be_hidden()
    page.locator('#suite-menu-btn').click()
    page.locator('#suite-menu-trash').click()
    page.locator('[data-id="trash-purge"]').click()
    expect(page.locator('[data-id="trash-purge-confirm"]')).to_be_visible()
    page.locator('[data-id="trash-purge-cancel"]').click()
    expect(page.locator('[data-id="trash-restore"]')).to_be_visible()
    page.locator('[data-id="trash-purge"]').click()
    page.locator('[data-id="trash-purge-confirm"]').click()
    expect(page.locator('[data-id="trash-empty"]')).to_be_visible()


def test_tc_dialog_tab_wraps_in_both_directions(page, tc_server):
    studio(page, tc_server)
    page.locator('#btn-import-xlsx').click()
    page.locator('#import-plan').is_disabled()
    page.locator('#import-cancel').focus()
    page.keyboard.press('Tab')
    expect(page.locator('#import-close')).to_be_focused()
    page.keyboard.press('Shift+Tab')
    expect(page.locator('#import-cancel')).to_be_focused()
    page.keyboard.press('Escape')
    expect(page.locator('#btn-import-xlsx')).to_be_focused()


def test_md_group_preview_commit_conflict_choices_and_rollback(page, tc_server):
    import _tc_library as lib
    import _paths
    from _tc_model import new_case
    case = new_case(case_id='AUD_0001',sheet='Sheet',path=['Audit','',''],feature='Verified case',
        steps=['Tap'],expected='Screen appears',status='approved',platforms=['ios'],results={'ios':''})
    lib.import_cases('md-audit',['Sheet'],[case],'seed')
    studio(page, tc_server)
    page.locator('#suite-select').select_option('md-audit')
    page.locator('[data-id="nav-tab-export"]').click()
    page.locator('[data-id="md-map-group"]').fill('audit')
    page.locator('[data-id="md-map-code"]').fill('AUD')
    page.locator('[data-id="md-map-fix"]').click()
    expect(page.locator('#md-groups')).to_contain_text('매핑됨')
    page.locator('#md-preview').click()
    expect(page.locator('#md-preview-panel')).to_be_visible()
    page.locator('#md-commit').click()
    expect(page.locator('#md-result')).to_be_visible()
    target = next(_paths.TESTCASES_DIR.rglob('*.md'))
    assert target.relative_to(_paths.TESTCASES_DIR).parts[:2] == ('ios','audit')
    page.locator('#md-rollback').click()
    expect(page.locator('#md-preview-panel')).to_be_hidden()
    assert not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('Preserve manual edit')
    page.locator('#md-preview').click()
    expect(page.locator('[data-id="md-conflict-decision"]')).to_be_visible()
    page.locator('#md-commit').click()
    expect(page.locator('#md-result')).to_be_visible()
    assert target.read_text() == 'Preserve manual edit'
    page.locator('#md-preview-back').click()
    page.locator('#md-preview').click()
    page.locator('[data-id="md-conflict-decision"]').select_option('overwrite')
    page.locator('#md-commit').click()
    expect(page.locator('#md-result')).to_be_visible()
    assert 'Verified case' in target.read_text()
    page.locator('#md-rollback').click()
    expect(page.locator('#md-preview-panel')).to_be_hidden()
    assert target.read_text() == 'Preserve manual edit'


def test_authoring_sheet_branch_profile_paste_and_cancel_mocked_job(page, tc_server):
    studio(page, tc_server)
    page.locator('#gen-add-sheet').click()
    page.locator('#sheet-rename-name').fill('Audit sheet')
    page.locator('#sheet-rename-save').click()
    expect(page.locator('#gen-target-sheet')).to_have_value('Audit sheet')
    page.locator('#gen-path-l1').select_option('__new')
    page.locator('#gen-new-l1').fill('Audit group')
    page.locator('#gen-add-branch').click()
    expect(page.locator('#gen-path-l1')).to_have_value('Audit group')
    page.locator('#gen-profile-edit').click()
    page.locator('#gen-profile-name').fill('Audit profile')
    page.locator('#gen-rules-input').fill('Only write documented requirements')
    page.locator('#gen-banned-input').fill('ambiguous')
    page.locator('#gen-endings-input').fill('된다.')
    page.locator('#gen-profile-save').click()
    expect(page.locator('#gen-profile')).to_have_value('Audit profile')
    page.locator('[data-id="src-tab-paste"]').click()
    page.locator('#src-paste').fill('# Audit\n\n버튼을 누르면 결과 화면이 표시된다.')
    page.locator('#src-paste-add').click()
    expect(page.locator('[data-id="src-chip"]')).to_have_count(1)
    expect(page.locator('#gen-submit')).to_be_enabled()
    page.evaluate('''() => {
        window.auditJobStatus='queued';window.auditJobWrites=[];
        const job = () => ({job_id:'mock-audit',status:window.auditJobStatus,sections:[],kept:0,invalid:0,cost_usd:0});
        TCS_NS.api.startJob=async(s,p)=>{auditJobWrites.push({s,p});return {job:job()};};
        TCS_NS.api.job=async()=>({job:job(),log:'',invalid:[]});
        TCS_NS.api.cancelJob=async()=>{window.auditJobStatus='cancelled';return {ok:true};};
    }''')
    expect(page.locator('#tcs-toasts .toast')).to_have_count(0, timeout=7000)
    page.locator('#gen-submit').click()
    expect(page.locator('#job-cancel')).to_be_visible()
    assert page.evaluate('auditJobWrites[0].p.sheet') == 'Audit sheet'
    assert page.evaluate('auditJobWrites[0].p.profile') == 'Audit profile'
    page.locator('#job-cancel').click()
    expect(page.locator('#job-pill')).to_contain_text('취소', timeout=5000)
    page.locator('#job-dismiss').click()
    expect(page.locator('#job')).to_be_hidden()
    page.locator('[data-id="src-chip-remove"]').click()
    expect(page.locator('[data-id="src-chip"]')).to_have_count(0)
    expect(page.locator('#gen-submit')).to_be_disabled()


def test_excel_check_response_cannot_reenable_download_after_input_changes(page):
    page.set_content('<div id="root" class="tc-studio"></div>')
    page.add_script_tag(path=str(STATIC / 'state.js'))
    page.evaluate("""() => {
        Object.assign(TCS_NS.state, {suite:'demo', suites:[{suite:'demo',count:1,sheets:['Sheet']}], tree:[]});
        TCS_NS.api={mdEligibility:async()=>({funnel:[{label:'all',count:0}],branches:[],drifted:[],excluded:[]}),
            exportXlsx:()=>new Promise(resolve=>window.finishCheck=()=>resolve({checks:[{level:'ok',message:'checked'}],filename:'old.xlsx',count:1,export_id:'old'}))};
    }""")
    page.add_script_tag(path=str(STATIC / 'export.js'))
    page.evaluate("""() => {const r=document.getElementById('root'); r.innerHTML=TCS_NS.exportView.html(); TCS_NS.exportView.mount(r); TCS_NS.exportView.onShow();}""")
    page.locator('#xlsx-run-check').click()
    page.locator('#xlsx-history-note').fill('Changed while checking')
    page.evaluate('finishCheck()')
    expect(page.locator('#xlsx-run-check')).to_be_enabled()
    expect(page.locator('#xlsx-download')).to_be_disabled()
    expect(page.locator('#xlsx-filename')).to_have_text('—')


def review_fixture(page, missing_target=False):
    from _tc_model import new_case
    from _tc_library import with_issues
    cases = [with_issues(new_case(case_id='AUD_0001',sheet='Sheet',path=['Audit','',''],feature='Duplicate draft',steps=['Tap'],expected='Screen appears',status='draft',
        draft_meta={'duplicates':[{'case_id':'OLD_0001','similarity':0.98}], 'duplicate_checked':False})),
        with_issues(new_case(case_id='AUD_0002',sheet='Sheet',path=['Audit','',''],feature='Clean draft',steps=['Tap'],expected='Screen appears',status='draft'))]
    target = with_issues(new_case(case_id='OLD_0001',sheet='Sheet',path=['Audit','',''],feature='Existing',steps=['Tap'],expected='Old screen',status='approved'))
    page.set_content('<div id="root" class="tc-studio"></div><div id="tcs-toasts"></div>')
    page.add_script_tag(path=str(STATIC/'state.js'))
    page.evaluate('''data => {
        Object.assign(TCS_NS.state,{suite:'review-audit', screen:'review'});
        window.cases=data.cases;window.decisions=[];
        TCS_NS.refreshCounts=async()=>{};
        TCS_NS.api={list:async()=>({items:cases.filter(c=>c.status==='draft'),total:cases.filter(c=>c.status==='draft').length}),
            getCase:async(s,id)=>{if(data.missing)throw Object.assign(new Error('Deleted'),{status:404});return {case:data.target};},
            coverage:async()=>({features:[]}),
            patchCase:async(s,id,rev,patch)=>{decisions.push({id,patch});Object.assign(cases.find(c=>c.case_id===id),patch);return {case:cases.find(c=>c.case_id===id)};},
            resolveDuplicate:async(s,id,p)=>{decisions.push({id,duplicate:p.action});cases.find(c=>c.case_id===id).draft_meta={duplicates:[],duplicate_checked:true};return {ok:true};}
        };
    }''', {'cases':cases,'target':target,'missing':missing_target})
    page.add_script_tag(path=str(STATIC/'review.js'))
    page.evaluate('''() => {const root=document.getElementById('root');root.innerHTML=TCS_NS.reviewView.html();TCS_NS.reviewView.mount(root);TCS_NS.reviewView.onShow();}''')


def test_review_duplicate_resolution_approval_and_rejection(page):
    review_fixture(page)
    expect(page.locator('[data-id="draft-card"]')).to_have_count(2)
    first=page.locator('[data-id="draft-card"]').first
    expect(first.locator('[data-id="draft-approve"]')).to_be_disabled()
    first.locator('[data-id="dup-add"]').click()
    expect(page.locator('[data-id="draft-card"]').first.locator('[data-id="draft-approve"]')).to_be_enabled()
    page.locator('[data-id="draft-card"]').first.locator('[data-id="draft-approve"]').click()
    expect(page.locator('[data-id="draft-card"]')).to_have_count(1)
    page.locator('[data-id="draft-reject"]').click()
    expect(page.locator('[data-id="draft-card"]')).to_have_count(0)
    assert page.evaluate('decisions') == [
        {'id':'AUD_0001','duplicate':'add'}, {'id':'AUD_0001','patch':{'status':'approved'}},
        {'id':'AUD_0002','patch':{'status':'rejected'}}]


def test_deleted_duplicate_candidate_keeps_draft_reviewable(page):
    review_fixture(page, missing_target=True)
    expect(page.locator('[data-id="draft-card"]')).to_have_count(2)
    first=page.locator('[data-id="draft-card"]').first
    expect(first).to_contain_text('삭제')
    expect(first.locator('[data-id="dup-update"]')).to_have_count(0)
    first.locator('[data-id="dup-add"]').click()
    expect(page.locator('[data-id="draft-card"]').first.locator('[data-id="draft-approve"]')).to_be_enabled()


def test_connections_and_remote_collection_use_mocked_services_only(page, tc_server):
    import json
    state={'confluence':{'configured':False},'figma':{'configured':False}}
    writes=[]
    def credentials(route):
        if route.request.method=='PUT':
            kind=route.request.url.rsplit('/',1)[-1]
            writes.append((kind,route.request.post_data_json))
            state[kind]={'configured':True,'base_url':'https://company.atlassian.net','deployment':'cloud'}
        route.fulfill(json=state)
    studio(page, tc_server)
    page.route('**/api/tc-library/credentials**',credentials)
    page.locator('#cred-settings').click()
    page.locator('#cred-base').fill('https://company.atlassian.net')
    page.locator('#cred-email').fill('qa@example.com')
    page.locator('#cred-conf-token').fill('mock-confluence-token')
    page.locator('#cred-figma-token').fill('mock-figma-token')
    page.locator('#cred-save').click()
    expect(page.locator('#cred-modal')).to_be_hidden()
    expect(page.locator('[data-id="cred-status-confluence"]')).to_contain_text('연결됨')
    expect(page.locator('[data-id="cred-status-figma"]')).to_contain_text('연결됨')
    assert len(writes)==2
    assert writes[0][1]['deployment']=='cloud'
    collected=[]
    def collect(route):
        kind=route.request.url.rsplit('/',1)[-1]
        collected.append((kind,route.request.post_data_json))
        source={'source_id':kind,'kind':kind,'title':kind,'ref':kind+':mock','chars':20,'sections':1,'warnings':[],'version':'v1'}
        route.fulfill(json={'sources':[source]} if kind=='confluence' else {'source':source})
    for kind in ['url','confluence','figma']:
        page.route(f'**/api/tc-library/sources/*/{kind}',collect)
        page.locator(f'[data-id="src-tab-{kind}"]').click()
        page.locator(f'#src-{kind}-url').fill('https://example.com/mock')
        if kind=='confluence':page.locator('#src-confluence-children').check()
        page.locator(f'#src-{kind}-fetch').click()
    expect(page.locator('[data-id="src-chip"]')).to_have_count(3)
    assert collected[1][1]['children'] is True
    page.locator('[data-id="src-tab-url"]').click()
    page.locator('#src-url-url').fill('not-a-url')
    page.locator('#src-url-fetch').click()
    expect(page.locator('#src-url-url')).to_have_class('input error')
    assert len(collected)==3


def test_review_bulk_approval_excludes_unresolved_duplicate(page):
    review_fixture(page)
    page.evaluate('''() => {
        TCS_NS.api.bulk=async(s,items)=>{window.bulkCases=items.map(x=>x.case_id);items.forEach(x=>cases.find(c=>c.case_id===x.case_id).status='approved');return {updated:items};};
    }''')
    expect(page.locator('[data-id="draft-card"]')).to_have_count(2)
    page.locator('#review-approve-clean').click()
    expect(page.locator('[data-id="draft-card"]')).to_have_count(1)
    assert page.evaluate('bulkCases') == ['AUD_0002']
    expect(page.locator('[data-id="draft-approve"]')).to_be_disabled()


def test_grid_edit_refreshes_the_current_search_result(page, tc_server):
    import _tc_library as lib
    from _tc_model import new_case
    lib.import_cases('filter-audit',['Sheet'],[new_case(case_id='AUD_0001',sheet='Sheet',path=['Audit','',''],feature='Filter current'),
        new_case(case_id='AUD_0002',sheet='Sheet',path=['Audit','',''],feature='Other case')],'seed')
    studio(page, tc_server)
    page.locator('#suite-select').select_option('filter-audit')
    page.locator('[data-id="nav-tab-library"]').click()
    page.locator('#lib-search').fill('Filter current')
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(1)
    cell=page.locator('[data-id="grid-cell-feature"]')
    cell.dblclick();cell.fill('Filter changed');cell.press('Meta+Enter')
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(0)
    page.locator('#lib-search').fill('Filter changed')
    expect(page.locator('#grid-body tr[data-case]')).to_have_count(1)
    expect(page.locator('[data-id="grid-cell-feature"]')).to_have_text('Filter changed')


def detail_fixture(page):
    from _tc_model import new_case
    from _tc_library import with_issues
    case=with_issues(new_case(case_id='AUD_0001',sheet='Sheet',path=['Audit','',''],feature='Server title',steps=['Tap'],expected='Visible'))
    page.set_content('<div id="root"><div id="lib" class="no-detail"><table><tbody id="grid-body"></tbody></table><div id="detail-host"></div></div></div><div id="tcs-toasts"></div>')
    page.add_script_tag(path=str(STATIC/'state.js'))
    page.evaluate('''c=>{
      window.detailCase=c; Object.assign(TCS_NS.state,{suite:'detail-audit',items:[c]});
      TCS_NS.library={refresh:async()=>{},reloadList:async()=>{}};
      TCS_NS.api={getCase:async()=>({case:detailCase}),history:async()=>({history:[]})};
    }''',case)
    page.add_script_tag(path=str(STATIC/'detail.js'))
    page.evaluate('''()=>{const root=document.getElementById('root');document.getElementById('detail-host').innerHTML=TCS_NS.detail.html();TCS_NS.detail.mount(root);}''')


def test_delayed_detail_refresh_preserves_user_typing(page):
    detail_fixture(page)
    page.evaluate("TCS_NS.detail.open('AUD_0001')")
    page.evaluate('''()=>{TCS_NS.api.getCase=()=>new Promise(resolve=>window.finishDetail=()=>resolve({case:detailCase}));TCS_NS.detail.refreshIfOpen();}''')
    page.locator('#detail-feature').fill('Unsaved user input')
    page.evaluate('finishDetail()')
    expect(page.locator('#detail-feature')).to_have_value('Unsaved user input')
    expect(page.locator('#detail-save')).to_be_enabled()


def test_older_detail_request_cannot_replace_newer_case(page):
    detail_fixture(page)
    page.evaluate('''()=>{
      window.detailReplies={};TCS_NS.api.getCase=(s,id)=>new Promise(resolve=>detailReplies[id]=()=>resolve({case:{...detailCase,case_id:id,feature:id}}));
      TCS_NS.detail.open('AUD_0001');TCS_NS.detail.open('AUD_0002');
    }''')
    page.evaluate("detailReplies['AUD_0002']()")
    expect(page.locator('#detail-feature')).to_have_value('AUD_0002')
    page.evaluate("detailReplies['AUD_0001']()")
    expect(page.locator('#detail-feature')).to_have_value('AUD_0002')


def test_delayed_detail_response_does_not_reopen_closed_panel(page):
    detail_fixture(page)
    page.evaluate("TCS_NS.detail.open('AUD_0001')")
    page.evaluate('''()=>{TCS_NS.api.getCase=()=>new Promise(resolve=>window.finishDetail=()=>resolve({case:detailCase}));TCS_NS.detail.refreshIfOpen();}''')
    page.locator('#detail-close').click()
    expect(page.locator('#lib')).to_have_class('no-detail')
    page.evaluate('finishDetail()')
    expect(page.locator('#lib')).to_have_class('no-detail')
    assert page.evaluate('TCS_NS.state.activeId') == ''


def test_save_unsaved_changes_then_open_the_requested_case(page):
    detail_fixture(page)
    page.evaluate('''()=>{
      document.getElementById('root').insertAdjacentHTML('beforeend','<div id="dirty-modal" hidden><span id="dirty-title"></span><button id="dirty-save">저장하고 이동</button><button id="dirty-discard">버리고 이동</button><button id="dirty-cancel">취소</button></div>');
      TCS_NS.api.getCase=async(s,id)=>({case:{...detailCase,case_id:id,feature:id}});
      TCS_NS.api.patchCase=async(s,id,rev,changes)=>({case:{...detailCase,case_id:id,...changes,rev:rev+1}});
      TCS_NS.library.refresh=async()=>{await TCS_NS.detail.refreshIfOpen();};
    }''')
    page.evaluate("TCS_NS.detail.open('AUD_0001')")
    page.locator('#detail-feature').fill('Saved before moving')
    page.evaluate("void TCS_NS.detail.open('AUD_0002')")
    page.locator('#dirty-save').click()
    expect(page.locator('#detail-feature')).to_have_value('AUD_0002')
    assert page.evaluate('TCS_NS.state.activeId') == 'AUD_0002'
