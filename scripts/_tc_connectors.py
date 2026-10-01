"""원격 소스 수집 — PRD URL · Confluence · Figma (PRD F1.3, F1.4, 로드맵 C3~C5).

모든 요청은 _tc_fetch.fetch()를 거친다 (호스트 허용 목록·내부망 차단·리다이렉트 재검사·크기 상한).
사용자가 준 URL은 **id를 뽑는 데만** 쓰고, API 요청 주소는 서버가 설정값으로 조립한다.

ref 형식 (버전 포함):
  url:{본문 sha256 12자}            (version = 같은 값)
  conf:{page_id}@v{version.number}
  figma:{file_key}/{node_id|file}@{figma version}
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import _tc_credentials as creds
from _tc_fetch import FetchError, Policy, fetch
from _tc_html import html_title, to_markdown
from _tc_sources import add_fetched, extract

FIGMA_API = "https://api.figma.com"
FIGMA_IMAGE_HOSTS = ("figma-alpha-api.s3.us-west-2.amazonaws.com", "*.figma.com")
MAX_FIGMA_TEXTS = 2000
MAX_FIGMA_FRAMES = 10
MAX_CHILD_PAGES = 20


# ── PRD URL (공개 HTTPS 문서) ─────────────────────────────────
def fetch_url(url: str) -> dict:
    """공개 문서 1건 → {title, markdown, version, origin, pages, warnings}. 모든 공개 호스트 허용(내부망은 차단)."""
    if urlparse(url).scheme != "https":
        raise FetchError("https 주소만 가져올 수 있습니다", "URL_NOT_ALLOWED")
    resp = fetch(url, Policy(hosts=("*",)))
    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    name = unquote(urlparse(resp.url).path.rsplit("/", 1)[-1]) or "document"
    if ctype == "application/pdf" or name.lower().endswith(".pdf"):
        markdown, pages, warnings = extract("remote.pdf", resp.body)
        title = name
    elif "wordprocessingml" in ctype or name.lower().endswith(".docx"):
        markdown, pages, warnings = extract("remote.docx", resp.body)
        title = name
    elif ctype in ("text/html", "application/xhtml+xml") or not ctype:
        html = resp.text()
        markdown, pages, warnings = to_markdown(html), 0, []
        title = html_title(html) or urlparse(url).hostname
    elif ctype.startswith("text/"):
        markdown, pages, warnings = resp.text(), 0, []
        title = name
    else:
        raise FetchError(f"지원하지 않는 문서 형식입니다: {ctype}", "UNSUPPORTED_REMOTE_TYPE")
    version = hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:12]
    return {"title": title, "markdown": markdown, "version": version, "origin": url,
            "pages": pages, "warnings": warnings}


def add_url(bundle_id: str, url: str) -> dict:
    doc = fetch_url(url)
    return add_fetched(bundle_id, kind="url", title=doc["title"], markdown=doc["markdown"],
                       ref=f"url:{doc['version']}", version=doc["version"], origin=url,
                       pages=doc["pages"], warnings=doc["warnings"])


# ── Confluence ───────────────────────────────────────────────
def _conf_policy(cfg: dict) -> Policy:
    host = urlparse(cfg["base_url"]).hostname or ""
    return Policy(hosts=(host,), private_hosts=(host,) if cfg["allow_private"] else (),
                  http_hosts=(host,) if cfg["base_url"].startswith("http://") else (),
                  headers=creds.confluence_headers(cfg))


def _api_root(cfg: dict) -> str:
    base = cfg["base_url"]
    if cfg["deployment"] == "cloud":
        return base if base.endswith("/wiki") else base + "/wiki"
    return base


def parse_confluence_url(url: str, cfg: dict) -> dict:
    """→ {"page_id"} 또는 {"space", "title"} 또는 {"tiny"}. 설정한 base와 다른 호스트면 거부."""
    parsed = urlparse(url)
    base_host = urlparse(cfg["base_url"]).hostname
    if not base_host:
        raise FetchError("Confluence 연결이 설정되지 않았습니다", "CREDENTIALS_MISSING", 409)
    if (parsed.hostname or "").lower() != base_host.lower():
        raise FetchError(f"설정한 Confluence 주소({base_host})의 페이지가 아닙니다", "HOST_NOT_ALLOWED")
    if m := re.search(r"/pages/(\d+)", parsed.path):
        return {"page_id": m.group(1)}
    if page_id := parse_qs(parsed.query).get("pageId", [""])[0]:
        if page_id.isdigit():
            return {"page_id": page_id}
    if m := re.search(r"/x/([A-Za-z0-9_-]+)", parsed.path):
        return {"tiny": m.group(1)}
    if m := re.search(r"/display/([^/]+)/([^/?#]+)", parsed.path):
        return {"space": unquote(m.group(1)), "title": unquote(m.group(2)).replace("+", " ")}
    raise FetchError("페이지 ID를 찾을 수 없습니다. /pages/{id} 또는 pageId= 가 들어간 주소를 넣어 주세요",
                     "PAGE_ID_NOT_FOUND")


def _resolve_page_id(target: dict, cfg: dict) -> str:
    if "page_id" in target:
        return target["page_id"]
    root, policy = _api_root(cfg), _conf_policy(cfg)
    if "tiny" in target:                       # /x/{tiny}는 같은 호스트의 /pages/{id}로 리다이렉트된다
        resp = fetch(f"{root}/x/{quote(target['tiny'])}", policy)
        if m := re.search(r"/pages/(\d+)", resp.url) or re.search(r"pageId=(\d+)", resp.url):
            return m.group(1)
        raise FetchError("짧은 링크에서 페이지를 찾지 못했습니다", "PAGE_ID_NOT_FOUND")
    path = "/rest/api/content"
    query = urlencode({"spaceKey": target["space"], "title": target["title"], "limit": 1})
    results = fetch(f"{root}{path}?{query}", policy).json().get("results", [])
    if not results:
        raise FetchError("제목으로 페이지를 찾지 못했습니다", "NOT_FOUND_REMOTE", 404)
    return str(results[0]["id"])


def fetch_confluence_page(page_id: str, cfg: dict) -> dict:
    """→ {page_id, title, version, markdown}."""
    root, policy = _api_root(cfg), _conf_policy(cfg)
    if cfg["deployment"] == "cloud":
        data = fetch(f"{root}/api/v2/pages/{page_id}?body-format=storage", policy).json()
        html = data["body"]["storage"]["value"]
    else:
        data = fetch(f"{root}/rest/api/content/{page_id}?expand=body.storage,version", policy).json()
        html = data["body"]["storage"]["value"]
    return {"page_id": str(data["id"]), "title": data["title"], "version": int(data["version"]["number"]),
            "markdown": to_markdown(html)}


def confluence_version(page_id: str, cfg: dict) -> int:
    root, policy = _api_root(cfg), _conf_policy(cfg)
    url = (f"{root}/api/v2/pages/{page_id}" if cfg["deployment"] == "cloud"
           else f"{root}/rest/api/content/{page_id}?expand=version")
    return int(fetch(url, policy).json()["version"]["number"])


def _child_ids(page_id: str, cfg: dict) -> list[str]:
    root, policy = _api_root(cfg), _conf_policy(cfg)
    url = (f"{root}/api/v2/pages/{page_id}/children?limit={MAX_CHILD_PAGES}" if cfg["deployment"] == "cloud"
           else f"{root}/rest/api/content/{page_id}/child/page?limit={MAX_CHILD_PAGES}")
    return [str(r["id"]) for r in fetch(url, policy).json().get("results", [])][:MAX_CHILD_PAGES]


def add_confluence(bundle_id: str, url: str, *, children: bool = False) -> list[dict]:
    cfg = creds.confluence()
    page_id = _resolve_page_id(parse_confluence_url(url, cfg), cfg)
    ids = [page_id] + (_child_ids(page_id, cfg) if children else [])
    entries = []
    for pid in ids:
        page = fetch_confluence_page(pid, cfg)
        origin = f"{_api_root(cfg)}/pages/viewpage.action?pageId={pid}"
        entries.append(add_fetched(bundle_id, kind="conf", title=page["title"], markdown=page["markdown"],
                                   ref=f"conf:{pid}@v{page['version']}", version=f"v{page['version']}",
                                   origin=origin))
    return entries


# ── Figma ────────────────────────────────────────────────────
def parse_figma_url(url: str) -> dict:
    parsed = urlparse(url)
    if not (parsed.hostname or "").endswith("figma.com"):
        raise FetchError("Figma 파일 주소가 아닙니다", "HOST_NOT_ALLOWED")
    m = re.match(r"/(?:file|design|proto)/([A-Za-z0-9]+)", parsed.path)
    if not m:
        raise FetchError("Figma 파일 주소가 아닙니다. /file/ 또는 /design/ 주소를 넣어 주세요", "FIGMA_KEY_NOT_FOUND")
    node = parse_qs(parsed.query).get("node-id", [""])[0].replace("-", ":")
    return {"file_key": m.group(1), "node_id": node if re.fullmatch(r"\d+:\d+", node) else ""}


def _figma_policy(hosts=("api.figma.com",)) -> Policy:
    return Policy(hosts=hosts, headers=creds.figma_headers())


def _walk(node: dict, frame: str, out: dict, names: dict) -> None:
    names[node.get("id", "")] = node.get("name", "")
    kind = node.get("type")
    if kind == "TEXT" and node.get("characters", "").strip() and len(out["texts"]) < MAX_FIGMA_TEXTS:
        out["texts"].append((frame, node["characters"].strip()))
    elif kind == "INSTANCE":
        props = node.get("componentProperties") or {}
        variants = ", ".join(f"{k.split('#')[0]}={v.get('value')}" for k, v in props.items()
                             if v.get("type") == "VARIANT")
        out["components"].append((frame, node.get("name", ""), variants))
    targets = [node.get("transitionNodeID")] + [
        (i.get("actions") or [{}])[0].get("destinationId") for i in node.get("interactions") or []]
    for target in filter(None, targets):
        out["flows"].append((frame, node.get("name", ""), target))
    for child in node.get("children") or []:
        _walk(child, frame, out, names)


def figma_outline(frames: list[dict]) -> str:
    """프레임 목록 → markdown (프레임 = 섹션). 화면 문구·컴포넌트 상태·프로토타입 이동을 적는다."""
    names: dict[str, str] = {}
    blocks = []
    for frame in frames:
        out = {"texts": [], "components": [], "flows": []}
        _walk(frame, frame.get("name", ""), out, names)
        blocks.append((frame, out))
    lines = []
    for frame, out in blocks:
        lines.append(f"# {frame.get('name', '프레임')}")
        lines += [f'- 화면 문구: "{t}"' for _, t in out["texts"]]
        lines += [f"- 컴포넌트: {n}{f' ({v})' if v else ''}" for _, n, v in out["components"]]
        lines += [f"- 이동: {src or '프레임'} 선택 → {names.get(dst, dst)}" for _, src, dst in out["flows"]]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def fetch_figma(url: str, *, images: bool = True) -> dict:
    """→ {file_key, node_id, name, version, markdown, frames[{id,name}], images{name: png bytes}}."""
    target = parse_figma_url(url)
    key, node = target["file_key"], target["node_id"]
    policy = _figma_policy()
    if node:
        data = fetch(f"{FIGMA_API}/v1/files/{key}/nodes?ids={quote(node)}&depth=6", policy).json()
        root = data["nodes"][node]["document"]
        frames = [root] if root.get("type") in ("FRAME", "COMPONENT", "SECTION") else \
            [c for c in root.get("children", []) if c.get("type") in ("FRAME", "COMPONENT")][:MAX_FIGMA_FRAMES]
    else:
        meta = fetch(f"{FIGMA_API}/v1/files/{key}?depth=2", policy).json()
        ids = [c["id"] for page in meta["document"].get("children", [])
               for c in page.get("children", []) if c.get("type") == "FRAME"][:MAX_FIGMA_FRAMES]
        if not ids:
            raise FetchError("가져올 프레임이 없습니다", "EMPTY_SOURCE")
        data = fetch(f"{FIGMA_API}/v1/files/{key}/nodes?ids={quote(','.join(ids))}&depth=6", policy).json()
        data.setdefault("version", meta.get("version"))
        data.setdefault("name", meta.get("name"))
        frames = [data["nodes"][i]["document"] for i in ids if i in data["nodes"]]
    pngs: dict[str, bytes] = {}
    if images and frames:
        ids = ",".join(f["id"] for f in frames[:MAX_FIGMA_FRAMES])
        urls = fetch(f"{FIGMA_API}/v1/images/{key}?ids={quote(ids)}&format=png&scale=1", policy).json().get("images", {})
        image_policy = Policy(hosts=FIGMA_IMAGE_HOSTS, max_bytes=10 * 1024 * 1024)
        for frame in frames[:MAX_FIGMA_FRAMES]:
            if urls.get(frame["id"]):
                pngs[frame.get("name", frame["id"])] = fetch(urls[frame["id"]], image_policy).body
    return {"file_key": key, "node_id": node, "name": data.get("name", key), "version": str(data.get("version", "")),
            "markdown": figma_outline(frames), "frames": [{"id": f["id"], "name": f.get("name", "")} for f in frames],
            "images": pngs}


def figma_version(file_key: str) -> str:
    return str(fetch(f"{FIGMA_API}/v1/files/{file_key}?depth=1", _figma_policy()).json().get("version", ""))


def add_figma(bundle_id: str, url: str) -> dict:
    doc = fetch_figma(url)
    node = doc["node_id"] or "file"
    title = doc["name"] + (f" / {doc['frames'][0]['name']}" if doc["node_id"] and doc["frames"] else "")
    warnings = [] if doc["images"] else ["프레임 이미지를 받지 못했습니다"]
    return add_fetched(bundle_id, kind="figma", title=title, markdown=doc["markdown"],
                       ref=f"figma:{doc['file_key']}/{node}@{doc['version']}", version=doc["version"],
                       origin=url, warnings=warnings, assets=doc["images"])


def ref_base(ref: str) -> str:
    """"conf:123@v14#§2" → "conf:123", "figma:KEY/1:2@99#§1" → "figma:KEY/1:2"."""
    return ref.split("#", 1)[0].split("@", 1)[0]


def current_version(ref: str) -> str:
    """버전 포함 ref의 현재 원격 버전 (conf → "v15", figma → 버전 id, url → 본문 해시)."""
    base = ref_base(ref)
    kind, _, rest = base.partition(":")
    if kind == "conf":
        return f"v{confluence_version(rest, creds.confluence())}"
    if kind == "figma":
        return figma_version(rest.split("/", 1)[0])
    raise FetchError(f"버전을 확인할 수 없는 출처입니다: {kind}", "UNSUPPORTED_REF")


def refetch_markdown(ref: str) -> str:
    """현재 버전 본문 (차이 비교용)."""
    base = ref_base(ref)
    kind, _, rest = base.partition(":")
    if kind == "conf":
        return fetch_confluence_page(rest, creds.confluence())["markdown"]
    if kind == "figma":
        key, _, node = rest.partition("/")
        url = f"https://www.figma.com/design/{key}/x" + (f"?node-id={node.replace(':', '-')}" if node != "file" else "")
        return fetch_figma(url, images=False)["markdown"]
    raise FetchError(f"다시 가져올 수 없는 출처입니다: {kind}", "UNSUPPORTED_REF")
