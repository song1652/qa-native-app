"""HTML·Confluence storage 포맷 → markdown (표준 라이브러리 html.parser만 사용).

지원: h1~h6(→ #~###), p·br, ul/ol·li, table(→ markdown 표, 셀 안 줄바꿈은 공백), pre·code,
Confluence 매크로(info·note·warning·panel·expand·code의 본문은 살리고 제목을 붙인다),
ac:image + ri:attachment(→ "[이미지: 파일명]"), ac:link + ri:page(→ 페이지 제목 텍스트).
script·style·nav·header·footer·ac:parameter는 버린다.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOCK = {"p", "div", "section", "article", "blockquote", "br", "hr"}
_SKIP = {"script", "style", "nav", "header", "footer", "noscript", "ac:parameter", "svg"}
_MACRO_TITLE = {"info": "정보", "note": "참고", "warning": "주의", "tip": "팁", "panel": "패널",
                "expand": "펼치기", "code": "코드"}


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[tuple[str, str, str]] = []   # (앞 구분자, 텍스트, 종류 block|list)
        self.line: list[str] = []
        self.next_sep = "\n\n"
        self.skip = 0
        self.lists: list[list] = []          # [kind, counter]
        self.table: list[list[str]] | None = None
        self.cell: list[str] | None = None
        self.heading = 0
        self.pre = False

    # ── 줄 관리 ──
    def _flush(self) -> None:
        text = re.sub(r"[ \t]+", " ", "".join(self.line)).strip() if not self.pre else "".join(self.line)
        self.line = []
        if not text:
            return
        sep, self.next_sep = self.next_sep, "\n\n"
        if self.heading:
            text = "#" * min(self.heading, 3) + " " + text
        elif self.lists:
            kind, n = self.lists[-1]
            indent = "  " * (len(self.lists) - 1)
            text = f"{indent}{n}. {text}" if kind == "ol" else f"{indent}- {text}"
            if self.out and self.out[-1][2] == "list":
                sep = "\n"                  # 목록 항목끼리는 줄바꿈 하나
            self.out.append((sep, text, "list"))
            return
        self.out.append((sep, text, "block"))

    def _write(self, text: str) -> None:
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(text)
        else:
            self.line.append(text)

    # ── 태그 ──
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading = int(tag[1])
        elif tag in _BLOCK:
            if tag == "br" and self.cell is not None:
                self.cell.append(" ")
            elif tag == "br":
                self._flush()
                self.next_sep = "\n"       # <br>은 줄바꿈 하나
            else:
                self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists.append([tag, 0])
        elif tag == "li":
            self._flush()
            if self.lists:
                self.lists[-1][1] += 1
        elif tag == "table":
            self._flush()
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.table.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []
        elif tag == "pre":
            self._flush()
            self.pre = True
            self._emit("```")
            self.next_sep = "\n"
        elif tag == "ac:structured-macro":
            name = a.get("ac:name", "")
            if name in _MACRO_TITLE:
                self._flush()
                self._emit(f"> [{_MACRO_TITLE[name]}]")
        elif tag == "ri:attachment":
            self._write(f"[이미지: {a.get('ri:filename', '첨부')}]")
        elif tag == "ri:page":
            self._write(a.get("ri:content-title", ""))
        elif tag == "img":
            self._write(f"[이미지: {a.get('alt') or a.get('src', '').rsplit('/', 1)[-1]}]")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(self.skip - 1, 0)
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading = 0
        elif tag in _BLOCK or tag == "li":
            self._flush()
        elif tag in ("ul", "ol") and self.lists:
            self._flush()
            self.lists.pop()
        elif tag in ("td", "th") and self.cell is not None and self.table is not None:
            text = re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|")
            if self.table:
                self.table[-1].append(text)
            self.cell = None
        elif tag == "table" and self.table is not None:
            rows = [r for r in self.table if r]
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [""] * (width - len(r)) for r in rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
                lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                self._emit("\n".join(lines))
            self.table = None
        elif tag == "pre":
            self._flush()
            self.pre = False
            self.out.append(("\n", "```", "block"))

    def handle_data(self, data):
        if self.skip:
            return
        self._write(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ("br", "hr"):
            self.handle_endtag(tag)

    def _emit(self, text: str) -> None:
        self.out.append(("\n\n", text, "block"))

    def result(self) -> str:
        self._flush()
        joined = "".join((sep if i else "") + text for i, (sep, text, _) in enumerate(self.out))
        return re.sub(r"\n{3,}", "\n\n", joined).strip() + "\n"


def to_markdown(html: str) -> str:
    conv = _Converter()
    conv.feed(html)
    conv.close()
    return conv.result()


def html_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
