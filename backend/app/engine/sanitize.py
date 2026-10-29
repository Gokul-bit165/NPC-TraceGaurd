"""Turn untrusted email HTML into (visible text, hidden text, links).

Everything downstream, including the text model and any language-model narrator, sees only the
visible text. Hidden text (display:none, zero font size, white-on-white, comments) is kept apart so a
prompt-injection attempt aimed at an AI reviewer is detected as evidence instead of obeyed.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from .types import Link

_VOID = {"br", "img", "input", "meta", "link", "hr", "area", "base", "col", "embed", "source", "track", "wbr"}
_SKIP = {"script", "style", "head", "title"}
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­]")
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(px|pt|em|rem|%)?\s*(;|$)|opacity\s*:\s*0(\.0+)?\s*(;|$)"
    r"|max-height\s*:\s*0|height\s*:\s*0(px)?\s*;?.*overflow\s*:\s*hidden|color\s*:\s*(#fff(fff)?|white)\b.*background(-color)?\s*:\s*(#fff(fff)?|white)"
    r"|text-indent\s*:\s*-\d{3,}", re.I | re.S)


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.visible: list[str] = []
        self.hidden: list[str] = []
        self.links: list[Link] = []
        self._a_href: str | None = None
        self._a_text: list[str] = []
        self._a_hidden = False

    def _is_hidden(self) -> bool:
        return any(h for _, h in self.stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _VOID:
            if tag == "br":
                self.visible.append("\n")
            return
        hide = tag in _SKIP or "hidden" in a or (a.get("aria-hidden") == "true") or bool(_HIDDEN_STYLE.search(a.get("style") or ""))
        self.stack.append((tag, hide))
        if tag == "a" and a.get("href"):
            self._a_href, self._a_text, self._a_hidden = a["href"].strip(), [], self._is_hidden()

    def handle_endtag(self, tag):
        if tag == "a" and self._a_href is not None:
            text = re.sub(r"\s+", " ", "".join(self._a_text)).strip()
            if not self._a_hidden and not self._a_href.lower().startswith(("mailto:", "tel:", "#")):
                self.links.append(Link(href=self._a_href, text=text))
            self._a_href = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in {"p", "div", "tr", "li", "h1", "h2", "h3"}:
            self.visible.append("\n")

    def handle_data(self, data):
        if not data.strip():
            self.visible.append(" ")
            return
        if self._is_hidden():
            top_skip = any(t in _SKIP for t, _ in self.stack)
            if not top_skip:
                self.hidden.append(data.strip())
        else:
            self.visible.append(data)
            if self._a_href is not None:
                self._a_text.append(data)

    def handle_comment(self, data):
        if data.strip():
            self.hidden.append(data.strip())


def clean_text(s: str) -> str:
    s = _ZERO_WIDTH.sub("", s or "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def split_html(html: str) -> tuple[str, str, list[Link]]:
    p = _Extractor()
    try:
        p.feed(html or "")
        p.close()
    except Exception:  # malformed markup: fall back to a crude strip, treating everything as visible
        return clean_text(re.sub(r"<[^>]+>", " ", html or "")), "", []
    return clean_text("".join(p.visible)), clean_text(" ".join(p.hidden)), p.links


_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


def urls_in_text(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in _URL.findall(text or "")]


def find_terms(text: str, terms: list[str]) -> list[str]:
    low = (text or "").lower()
    return [t for t in terms if t in low]


def zero_width_count(raw: str) -> int:
    return len(_ZERO_WIDTH.findall(raw or ""))
