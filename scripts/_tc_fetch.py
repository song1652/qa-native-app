"""외부 문서 수집용 안전한 HTTP GET (PRD §7 SSRF, 로드맵 C1).

규칙:
- https만 허용한다. 예외: 사용자가 설정한 Confluence Server/DC base가 http이면 그 호스트만 http 허용.
- 호스트는 허용 목록과 맞아야 한다 ("*.atlassian.net"처럼 앞자리 와일드카드 1개 지원).
- DNS로 풀린 주소가 사설·루프백·링크로컬·예약 대역이면 거부한다.
  예외: allow_private=True로 명시한 호스트(사내 Confluence DC)만.
- 리다이렉트는 자동으로 따라가지 않는다. 최대 3번, 매번 위 검사를 다시 한다.
- 시간 제한 15초, 응답 크기 상한(기본 20MB). 넘으면 읽기를 멈추고 거부한다.

테스트는 모듈 전역 `transport`와 `resolver`를 바꿔 네트워크 없이 검증한다.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from _tc_library import LibraryError

TIMEOUT = 15
MAX_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 3


class FetchError(LibraryError):
    pass


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str

    def json(self):
        import json
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class Policy:
    """hosts: 허용 호스트 패턴. private_hosts: 사설 주소를 허용할 호스트(설정한 DC base). http_hosts: http 허용."""
    hosts: tuple[str, ...]
    private_hosts: tuple[str, ...] = ()
    http_hosts: tuple[str, ...] = ()
    max_bytes: int = MAX_BYTES
    headers: dict[str, str] = field(default_factory=dict)


def host_allowed(host: str, patterns: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    for pattern in patterns:
        pattern = pattern.lower()
        if pattern == "*":                      # 공개 문서 URL: 호스트는 자유, 내부망 검사는 그대로
            return True
        if pattern.startswith("*."):
            if host.endswith(pattern[1:]) and host != pattern[2:]:
                return True
        elif host == pattern:
            return True
    return False


def _resolve(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


resolver = _resolve


def _check(url: str, policy: Policy) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("https", "http") or not host:
        raise FetchError(f"지원하지 않는 주소입니다: {url}", "URL_NOT_ALLOWED")
    if parsed.scheme == "http" and host not in policy.http_hosts:
        raise FetchError("https 주소만 가져올 수 있습니다", "URL_NOT_ALLOWED")
    if parsed.username or parsed.password:
        raise FetchError("주소에 계정 정보를 넣을 수 없습니다", "URL_NOT_ALLOWED")
    if not host_allowed(host, policy.hosts):
        raise FetchError(f"허용되지 않은 호스트입니다: {host}", "HOST_NOT_ALLOWED")
    try:
        addresses = resolver(host)
    except OSError as exc:
        raise FetchError(f"주소를 찾을 수 없습니다: {host}", "DNS_FAILED") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        risky = ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved \
            or ip.is_multicast or ip.is_unspecified
        if risky and host not in policy.private_hosts:
            raise FetchError(f"내부망 주소로는 요청할 수 없습니다: {host} → {address}", "PRIVATE_ADDRESS")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # 리다이렉트는 fetch()가 직접 검사하며 따라간다
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _urlopen(url: str, headers: dict[str, str], max_bytes: int) -> Response:
    request = urllib.request.Request(url, headers={"User-Agent": "qa-native/1", **headers})
    try:
        resp = _opener.open(request, timeout=TIMEOUT)
    except urllib.error.HTTPError as err:          # 3xx·4xx·5xx도 응답으로 돌려준다
        resp = err
    with resp:
        body = resp.read(max_bytes + 1)
        return Response(resp.status if hasattr(resp, "status") else resp.code,
                        {k.lower(): v for k, v in resp.headers.items()}, body, url)


transport = _urlopen


def fetch(url: str, policy: Policy) -> Response:
    """GET 1회. 2xx가 아니면 FetchError. 리다이렉트는 검사하며 최대 3번 따라간다."""
    for _ in range(MAX_REDIRECTS + 1):
        _check(url, policy)
        try:
            resp = transport(url, policy.headers, policy.max_bytes)
        except (OSError, TimeoutError) as exc:
            raise FetchError(f"요청에 실패했습니다: {exc}", "FETCH_FAILED") from exc
        if len(resp.body) > policy.max_bytes:
            raise FetchError(f"응답이 {policy.max_bytes // (1024 * 1024)}MB를 넘습니다", "RESPONSE_TOO_LARGE", 413)
        if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("location"):
            url = urljoin(url, resp.headers["location"])
            continue
        if resp.status in (401, 403):
            raise FetchError("인증에 실패했습니다. 연결 설정의 토큰과 권한을 확인하세요", "AUTH_FAILED", 502)
        if resp.status == 404:
            raise FetchError("문서를 찾을 수 없습니다", "NOT_FOUND_REMOTE", 404)
        if not 200 <= resp.status < 300:
            raise FetchError(f"원격 서버 응답 {resp.status}", "REMOTE_ERROR", 502)
        return resp
    raise FetchError("리다이렉트가 너무 많습니다", "TOO_MANY_REDIRECTS", 502)
