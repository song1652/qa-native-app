"""Mirror taps use the visible image inside object-fit: contain. No device requests."""
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'agents/dashboard/static/capture-studio.js'


def setup_mirror(page, width, height):
    page.set_content(f'''<select id="cs-platform"><option>ios</option></select>
      <div style="position:relative"><img id="cs-mirror-img" style="width:{width}px;height:{height}px;object-fit:contain"
      src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='402' height='874'%3E%3Crect width='402' height='874' fill='white'/%3E%3C/svg%3E"
      onclick="csMirrorClick(event)"><div id="cs-crosshair"></div></div>''')
    page.add_script_tag(path=str(SCRIPT))
    page.evaluate('''()=>{
      window.tapRequests=[];window.hitCoordinates=[];
      window._csGetDeviceDimensions=()=>({w:402,h:874});
      window._csHierarchyDom={documentElement:{}};
      window.csFindSmallestNodeAt=(x,y)=>{hitCoordinates.push([x,y]);return null;};
      window.csStatusMsg=()=>{};
      window.fetch=async(url,options)=>{tapRequests.push({url,body:JSON.parse(options.body)});return {json:async()=>({ok:true})};};
    }''')
    page.wait_for_function('document.getElementById("cs-mirror-img").naturalWidth > 0')


@pytest.mark.parametrize('width,height,x,y,expected', [
    (278, 410, 87, 191, (90, 407)),
    (278, 410, 139, 205, (201, 437)),
    (200, 500, 100, 250, (201, 437)),
    (278, 410, 10, 191, None),
    (200, 500, 100, 10, None),
])
def test_mirror_tap_maps_visible_image_and_ignores_letterbox(page, width, height, x, y, expected):
    setup_mirror(page, width, height)
    page.locator('#cs-mirror-img').click(position={'x':x,'y':y})
    if expected is None:
        assert page.evaluate('tapRequests') == []
        assert page.evaluate('hitCoordinates') == []
    else:
        request = page.evaluate('tapRequests[0]')
        body = request['body']
        # Same scaling contract as /capture/tap; hierarchy and driver must agree.
        actual = (int(body['x'] * body['display_width'] / body['img_width']),
                  int(body['y'] * body['display_width'] / body['img_width']))
        assert request['url'] == '/capture/tap'
        assert actual == expected
        assert page.evaluate('hitCoordinates') == [list(expected)]


@pytest.mark.parametrize('start,end,expected', [
    ((87,191),(87,300),(90,407,90,640)),
    ((10,191),(87,300),None),
    ((87,191),(10,300),None),
])
def test_mirror_swipe_uses_the_same_visible_image_coordinates(page, start, end, expected):
    setup_mirror(page,278,410)
    page.add_script_tag(path=str(SCRIPT.parent/'capture-livetail.js'))
    page.evaluate("csLtAppend=()=>{}; const image=document.getElementById('cs-mirror-img');image.onclick=null;image.onmousedown=csMirrorMouseDown;image.onmousemove=csMirrorMouseMove;image.onmouseup=csMirrorMouseUp;")
    box=page.locator('#cs-mirror-img').bounding_box()
    page.mouse.move(box['x']+start[0],box['y']+start[1]);page.mouse.down()
    page.mouse.move(box['x']+end[0],box['y']+end[1]);page.mouse.up()
    if expected is None:
        assert page.evaluate('tapRequests') == []
    else:
        request=page.evaluate('tapRequests[0]');body=request['body']
        assert request['url'] == '/capture/scroll'
        assert (body['start_x'],body['start_y'],body['end_x'],body['end_y']) == expected
