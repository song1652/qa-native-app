from __future__ import annotations

import pytest

from _tc_fetch import FetchError, Policy, fetch, host_allowed
from _tc_html import html_title, to_markdown


def test_host_patterns():
    assert host_allowed("yafit.atlassian.net", ("*.atlassian.net",))
    assert not host_allowed("atlassian.net", ("*.atlassian.net",))
    assert not host_allowed("evil-atlassian.net", ("*.atlassian.net",))
    assert host_allowed("anything.example", ("*",))


def test_ssrf_defenses(fake_web):
    fake_web.add("https://docs.example.com/prd", "<p>ok</p>")
    assert fetch("https://docs.example.com/prd", Policy(hosts=("*",))).text() == "<p>ok</p>"

    cases = [
        ("http://docs.example.com/prd", Policy(hosts=("*",)), "URL_NOT_ALLOWED"),
        ("https://user:pw@docs.example.com/prd", Policy(hosts=("*",)), "URL_NOT_ALLOWED"),
        ("https://other.example.com/x", Policy(hosts=("docs.example.com",)), "HOST_NOT_ALLOWED"),
        ("file:///etc/passwd", Policy(hosts=("*",)), "URL_NOT_ALLOWED"),
    ]
    for url, policy, code in cases:
        with pytest.raises(FetchError) as exc:
            fetch(url, policy)
        assert exc.value.code == code, url

    fake_web.private.add("intranet.example.com")
    fake_web.add("https://intranet.example.com/x", "secret")
    with pytest.raises(FetchError) as exc:
        fetch("https://intranet.example.com/x", Policy(hosts=("*",)))
    assert exc.value.code == "PRIVATE_ADDRESS"
    assert fetch("https://intranet.example.com/x",
                 Policy(hosts=("intranet.example.com",), private_hosts=("intranet.example.com",))).text() == "secret"


def test_redirects_are_rechecked_and_limited(fake_web):
    fake_web.private.add("169.254.169.254")
    fake_web.add("https://docs.example.com/a", status=302, headers={"Location": "https://docs.example.com/b"})
    fake_web.add("https://docs.example.com/b", "final")
    fake_web.add("https://docs.example.com/meta", status=302, headers={"Location": "https://169.254.169.254/latest"})
    fake_web.add("https://docs.example.com/loop", status=302, headers={"Location": "/loop"})
    policy = Policy(hosts=("*",))

    resp = fetch("https://docs.example.com/a", policy)
    assert (resp.text(), resp.url) == ("final", "https://docs.example.com/b")
    with pytest.raises(FetchError) as exc:
        fetch("https://docs.example.com/meta", policy)
    assert exc.value.code == "PRIVATE_ADDRESS"
    with pytest.raises(FetchError) as exc:
        fetch("https://docs.example.com/loop", policy)
    assert exc.value.code == "TOO_MANY_REDIRECTS"


def test_size_cap_and_status_mapping(fake_web):
    fake_web.add("https://docs.example.com/big", b"x" * 2048)
    fake_web.add("https://docs.example.com/401", status=401)
    fake_web.add("https://docs.example.com/404", status=404)
    with pytest.raises(FetchError) as exc:
        fetch("https://docs.example.com/big", Policy(hosts=("*",), max_bytes=1024))
    assert exc.value.code == "RESPONSE_TOO_LARGE"
    for path, code in (("401", "AUTH_FAILED"), ("404", "NOT_FOUND_REMOTE")):
        with pytest.raises(FetchError) as exc:
            fetch(f"https://docs.example.com/{path}", Policy(hosts=("*",)))
        assert exc.value.code == code


def test_html_and_storage_to_markdown():
    html = ('<html><head><title>PRD 8.6</title><script>x()</script></head><body><nav>메뉴</nav>'
            '<h2>조건</h2><p>a<br>b</p><table><tr><th>조건</th><th>결과</th></tr><tr><td>1개</td><td>숨김 | 표시</td></tr></table>'
            '<ul><li>하나</li><li>둘<ol><li>셋</li></ol></li></ul>'
            '<ac:structured-macro ac:name="warning"><ac:parameter ac:name="title">t</ac:parameter>'
            '<ac:rich-text-body><p>주의 문구</p></ac:rich-text-body></ac:structured-macro>'
            '<ac:image><ri:attachment ri:filename="banner.png"/></ac:image></body></html>')
    md = to_markdown(html)
    assert html_title(html) == "PRD 8.6"
    assert "메뉴" not in md and "x()" not in md
    assert "## 조건\n\na\nb" in md
    assert "| 조건 | 결과 |\n|---|---|\n| 1개 | 숨김 \\| 표시 |" in md
    assert "- 하나\n- 둘\n  1. 셋" in md
    assert "> [주의]\n\n주의 문구" in md and "[이미지: banner.png]" in md
