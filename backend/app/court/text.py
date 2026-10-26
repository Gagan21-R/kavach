"""Turns untrusted policy input (plain text or HTML) into canonical visible text plus a record of hidden content.

Nothing here executes or obeys the input. Canonical text is what every agent cites; offsets refer to it.
"""
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

ZERO_WIDTH = "​‌‍⁠﻿᠎"
_ZW_RE = re.compile(f"[{ZERO_WIDTH}]")
_VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
_BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "tr", "ul", "ol", "table", "label", "button", "form"}
_SKIP = {"script", "style", "noscript", "template", "head", "title"}
_WHITE = {"#fff", "#ffffff", "white", "rgb(255,255,255)", "rgba(255,255,255,1)", "#fefefe", "#fffffe"}


@dataclass
class HiddenSegment:
    kind: str  # hidden_text, css_hidden, html_comment
    text: str
    reason: str


@dataclass
class Segment:
    """One run of text as it appears in the document, for rendering with hidden parts highlighted."""

    text: str
    hidden: bool
    reason: str = ""


@dataclass
class Extracted:
    canonical: str
    hidden: list[HiddenSegment] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    zero_width_count: int = 0
    was_html: bool = False


def _style_hidden(style: str) -> str | None:
    s = style.replace(" ", "").lower()
    if "display:none" in s:
        return "display:none"
    if "visibility:hidden" in s:
        return "visibility:hidden"
    if re.search(r"opacity:0(\.0+)?(;|$)", s):
        return "opacity:0"
    if re.search(r"font-size:0(px|pt|em|rem)?(;|$)", s):
        return "font-size:0"
    if re.search(r"(^|;)(height|width):0(px)?(;|$)", s) and "overflow:hidden" in s:
        return "zero-size box"
    if re.search(r"(left|top):-\d{3,}px", s):
        return "positioned off-screen"
    color = re.search(r"(?:^|;)color:([^;]+)", s)
    if color and color.group(1) in _WHITE:
        bg = re.search(r"background(?:-color)?:([^;]+)", s)
        if bg is None or bg.group(1) in _WHITE:
            return "white text on white background"
    return None


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []  # (tag, hidden_reason)
        self.skip_depth = 0
        self.segments: list[Segment] = []
        self.hidden: list[HiddenSegment] = []

    def _hidden_reason(self) -> str | None:
        for _, reason in reversed(self.stack):
            if reason:
                return reason
        return None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP:
            self.skip_depth += 1
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        reason = None
        if "hidden" in a:
            reason = "hidden attribute"
        elif a.get("aria-hidden") == "true":
            reason = "aria-hidden"
        elif a.get("type", "").lower() == "hidden":
            reason = "hidden input"
        elif "style" in a:
            reason = _style_hidden(a["style"])
        if tag in _BLOCK:
            self.segments.append(Segment("\n", False))
        if tag in ("input",) and a.get("value") and reason:
            self._text(a["value"], reason)
        if tag not in _VOID:
            self.stack.append((tag, reason))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in _BLOCK:
            self.segments.append(Segment("\n", False))

    def handle_data(self, data):
        if self.skip_depth:
            return
        self._text(data, self._hidden_reason())

    def _text(self, data, reason):
        if not data:
            return
        if reason:
            self.segments.append(Segment(data, True, reason))
            if data.strip():
                self.hidden.append(HiddenSegment("css_hidden" if "attribute" not in reason else "hidden_text", data.strip(), reason))
        else:
            self.segments.append(Segment(data, False))

    def handle_comment(self, data):
        if data.strip():
            self.hidden.append(HiddenSegment("html_comment", data.strip(), "HTML comment"))
            self.segments.append(Segment(f"<!-- {data.strip()} -->", True, "HTML comment"))


def looks_like_html(text: str) -> bool:
    return bool(re.search(r"<\s*(html|body|div|p|span|form|button|section|a|label|input|!--)\b", text, re.I))


def _normalize_ws(text: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in text.split("\n")]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if not blank and out:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()


def extract(raw: str) -> Extracted:
    zw = len(_ZW_RE.findall(raw))
    if looks_like_html(raw):
        p = _Parser()
        p.feed(raw)
        p.close()
        visible = "".join(s.text for s in p.segments if not s.hidden)
        canonical = _normalize_ws(_ZW_RE.sub("", visible))
        segments = [Segment(_ZW_RE.sub("", s.text), s.hidden, s.reason) for s in p.segments]
        return Extracted(canonical, p.hidden, _merge(segments), zw, True)
    canonical = _normalize_ws(_ZW_RE.sub("", raw))
    return Extracted(canonical, [], [Segment(canonical, False)], zw, False)


def _merge(segments: list[Segment]) -> list[Segment]:
    out: list[Segment] = []
    for s in segments:
        if out and out[-1].hidden == s.hidden and out[-1].reason == s.reason:
            out[-1] = Segment(out[-1].text + s.text, s.hidden, s.reason)
        else:
            out.append(s)
    return [Segment(re.sub(r"\n{3,}", "\n\n", s.text), s.hidden, s.reason) for s in out if s.text]


@dataclass(frozen=True)
class Clause:
    id: str
    start: int
    end: int
    text: str


# A sentence ends at . ! ? followed by whitespace or end of line, so dots inside "privacy@app.example" or
# "v1.2" do not split it. Lines without a terminator (headings) are clauses of their own.
_SENT = re.compile(r"[^\n]*?[.!?]+(?=\s|$)|[^\n]+$", re.M)


def split_clauses(canonical: str) -> list[Clause]:
    clauses = []
    for m in _SENT.finditer(canonical):
        raw = m.group(0)
        lead = len(raw) - len(raw.lstrip())
        text = raw.strip()
        if len(text) < 3:
            continue
        start = m.start() + lead
        clauses.append(Clause(f"c{len(clauses) + 1}", start, start + len(text), text))
    return clauses


def normalize_for_compare(text: str) -> str:
    t = _ZW_RE.sub("", text).lower()
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[–—]", "-", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([.,;:!?])", r"\1", t)
    return t.strip()
