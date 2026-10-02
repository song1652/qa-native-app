"""History filters reflect stored groups and survive list refreshes."""
from tests.dashboard.test_navigation_refresh import navigation_page  # noqa: F401


def seed_history(page):
    page.evaluate("""() => {
      localStorage.setItem('qa-native-app.run-history',JSON.stringify([
        {type:'quick',platform:'android',groups:['settings'],passed:1,total:1,failed:0,rate:100},
        {type:'pipeline',platform:'ios',groups:['new login'],passed:0,total:1,failed:1,rate:0}
      ]));renderRunHistory();
    }""")


def visible_count(page):
    return page.locator('#history-list .history-row').evaluate_all("rows=>rows.filter(row=>row.style.display!=='none').length")


def test_history_group_options_are_from_real_records(navigation_page):
    page=navigation_page
    seed_history(page)
    page.locator('.history-group-menu summary').click()
    page.locator('.history-filter.group[data-filter-value="new login"]').click()
    assert visible_count(page)==1
    assert page.locator('.history-group-menu summary').inner_text()=='new login'
    page.evaluate('renderRunHistory()')
    assert visible_count(page)==1
    assert page.locator('.history-filter.group.active').get_attribute('data-filter-value')=='new login'


def test_history_type_filter_survives_refresh_and_reset_restores_group_label(navigation_page):
    page=navigation_page
    seed_history(page)
    page.locator('.history-filter[data-filter-kind=type][data-filter-value=quick]').click()
    page.evaluate('renderRunHistory()')
    assert visible_count(page)==1
    page.locator('.history-group-menu summary').click()
    page.locator('.history-filter.group[data-filter-value=settings]').click()
    page.evaluate('window.dashboardConfirm=async()=>true;resetHistory()')
    assert page.locator('.history-group-menu summary').inner_text()=='전체 그룹'
    assert page.locator('#history-list').inner_text()=='실행 이력이 없습니다.'


def test_quick_select_all_syncs_run_button_and_partial_selection(navigation_page):
    page=navigation_page
    page.route('**/api/generated?platform=android',lambda route:route.fulfill(json=[{'platform':'android','count':2,'files':['settings/tc_a.py','login/tc_b.py']}]))
    page.evaluate('refreshGenerated()')
    page.locator('#quick-select-all').uncheck()
    assert page.locator('#quick-generated-run').is_disabled()
    page.locator('.quick-group-list .quick-group-cb').first.check()
    assert page.locator('#quick-generated-run').is_enabled()
    assert page.locator('#quick-select-all').evaluate('(el)=>el.indeterminate')
    page.locator('#quick-select-all').check()
    assert page.locator('.quick-group-list .quick-group-cb:checked').count()==2
    assert not page.locator('#quick-select-all').evaluate('(el)=>el.indeterminate')


def test_quick_platform_cannot_change_during_execution(navigation_page):
    page=navigation_page
    page.evaluate("window._quickRunActive=true;setQuickPlatform('ios')")
    assert page.evaluate('_quickPlatform')=='android'


def test_old_platform_response_cannot_replace_current_quick_fields(navigation_page):
    page=navigation_page
    page.evaluate("""() => {
      window.fetch=(url)=>new Promise(resolve=>{
        const platform=url.includes('ios')?'ios':'android';
        window['finish_'+platform]=()=>resolve({ok:true,json:async()=>[
          {platform,count:1,files:[platform+'/tc_example.py']}
        ]});
      });
      window.androidLoad=refreshGenerated();
      _quickPlatform='ios';window.iosLoad=refreshGenerated();
    }""")
    page.evaluate('async()=>{finish_ios();await iosLoad;}')
    page.evaluate('async()=>{finish_android();await androidLoad;}')
    assert page.evaluate('_generatedTests[0].platform')=='ios'
    assert page.locator('.quick-group-list .quick-group-cb').first.get_attribute('value')=='ios:ios'
