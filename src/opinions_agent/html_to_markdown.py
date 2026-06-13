"""Minimal stdlib HTML-to-markdown conversion for Reader document content."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "div", "section", "article", "br", "ul", "ol", "table", "tr"}
_SKIP_TAGS = {"script", "style", "head", "noscript", "svg", "iframe"}
_HEADING_PREFIX = {f"h{level}": "#" * level for level in range(1, 7)}


class _MarkdownExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._pre_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "pre":
            self._pre_depth += 1
            self._chunks.append("\n```\n")
        elif tag in _HEADING_PREFIX:
            self._chunks.append(f"\n\n{_HEADING_PREFIX[tag]} ")
        elif tag == "li":
            self._chunks.append("\n- ")
        elif tag == "blockquote":
            self._chunks.append("\n\n> ")
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "pre":
            self._pre_depth = max(0, self._pre_depth - 1)
            self._chunks.append("\n```\n")
        elif tag in _HEADING_PREFIX or tag in _BLOCK_TAGS:
            self._chunks.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._pre_depth:
            self._chunks.append(data)
        else:
            self._chunks.append(re.sub(r"\s+", " ", data))

    def text(self) -> str:
        joined = "".join(self._chunks)
        lines = [line.rstrip() for line in joined.splitlines()]
        collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        return collapsed.strip() + "\n" if collapsed.strip() else ""


def html_to_markdown(html: str) -> str:
    extractor = _MarkdownExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.text()
