"""
A small, deterministic CSS cascade resolver.

Why not Playwright? A headless browser gives you the truth, but it also gives
you a 130MB binary download, a per-run cold start, and a source of nondeterminism
(font availability, GPU rasterisation) right in the middle of an evaluation
harness. For a design-system conformance audit we need the *declared* computed
values, not a rasterised bitmap, and those can be resolved exactly.

So this module implements the parts of CSS that a component audit actually
touches: selector matching with real specificity, the cascade, inheritance,
custom properties with var() fallbacks, shorthand expansion, and state rules
(:hover / :focus / :focus-visible / :disabled) captured as separate style sets.

What it deliberately does NOT do: layout. It never computes used widths from
flow, so percentage lengths stay unresolved rather than guessed. See
`docs/ARCHITECTURE.md` for the full boundary and the Playwright adapter hook.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

from ..analyze.units import to_px

INHERITED = {
    "color", "font-family", "font-size", "font-weight", "font-style",
    "line-height", "letter-spacing", "text-align", "text-transform",
    "visibility", "white-space", "word-spacing",
}

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

STATE_PSEUDOS = {
    ":hover": "hover", ":focus": "focus", ":focus-visible": "focus",
    ":active": "active", ":disabled": "disabled",
}


# ---------------------------------------------------------------------------
# DOM
# ---------------------------------------------------------------------------
@dataclass
class Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Element"] = field(default_factory=list)
    parent: Optional["Element"] = None
    text: str = ""
    computed: dict[str, str] = field(default_factory=dict)
    computed_states: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    @property
    def el_id(self) -> Optional[str]:
        return self.attrs.get("id")

    @property
    def component(self) -> Optional[str]:
        """`data-ds-component` marks a node as a design-system component."""
        return self.attrs.get("data-ds-component")

    @property
    def role(self) -> str:
        explicit = self.attrs.get("data-ds-role") or self.attrs.get("role")
        if explicit:
            return explicit
        return {"button": "button", "input": "input", "a": "link",
                "h1": "heading", "h2": "heading", "h3": "heading",
                "h4": "heading", "p": "body", "label": "label",
                "li": "listitem", "span": "status", "section": "card",
                "article": "card", "textarea": "input", "select": "select"}.get(
                    self.tag, self.tag)

    def selector_path(self) -> str:
        bits = [self.tag]
        if self.el_id:
            bits.append(f"#{self.el_id}")
        for c in self.classes:
            bits.append(f".{c}")
        return "".join(bits)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


class _DomBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("html")
        self.stack = [self.root]
        self.style_blocks: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self._in_style = True
            return
        el = Element(tag, {k: (v or "") for k, v in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(el)
        if tag not in VOID_TAGS:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        el = Element(tag, {k: (v or "") for k, v in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(el)

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False
            return
        if tag in VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self._in_style:
            self.style_blocks.append(data)
        elif data.strip():
            self.stack[-1].text += data.strip() + " "


def parse_html(source: str) -> tuple[Element, list[str]]:
    b = _DomBuilder()
    b.feed(source)
    return b.root, b.style_blocks


# ---------------------------------------------------------------------------
# CSS parsing
# ---------------------------------------------------------------------------
@dataclass
class Rule:
    selector: str
    decls: dict[str, str]
    order: int
    media: str = ""
    state: str = "default"


_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_AT_RULE = re.compile(r"@(media|supports)([^{]*)\{", re.I)


def _split_top_level(css: str) -> list[tuple[str, str, str]]:
    """Yield (selector, body, media) handling one level of @media nesting."""
    css = _COMMENT.sub("", css)
    out: list[tuple[str, str, str]] = []
    i, n = 0, len(css)
    media_stack: list[str] = []
    buf = ""
    while i < n:
        ch = css[i]
        if ch == "{":
            head = buf.strip()
            buf = ""
            m = _AT_RULE.match(head + "{")
            if m:
                media_stack.append(m.group(2).strip())
                i += 1
                continue
            depth, j = 1, i + 1
            while j < n and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            body = css[i + 1: j - 1]
            out.append((head, body, media_stack[-1] if media_stack else ""))
            i = j
            continue
        if ch == "}":
            if media_stack:
                media_stack.pop()
            buf = ""
            i += 1
            continue
        buf += ch
        i += 1
    return out


def find_block(css: str, selector: str) -> Optional[tuple[int, int]]:
    """Byte span of the declaration body for an exact selector, or None."""
    m = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{", css, re.M)
    if not m:
        return None
    start, depth, i = m.end(), 1, m.end()
    while i < len(css) and depth:
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
        i += 1
    return start, i - 1


def parse_decls(body: str) -> dict[str, str]:
    """Public alias: parse a declaration body into a property map."""
    return _parse_decls(body)


def _parse_decls(body: str) -> dict[str, str]:
    decls: dict[str, str] = {}
    for chunk in body.split(";"):
        if ":" not in chunk:
            continue
        prop, _, val = chunk.partition(":")
        prop = prop.strip().lower()
        val = val.strip()
        if not prop or not val:
            continue
        val = re.sub(r"\s*!important\s*$", "", val, flags=re.I)
        decls[prop] = val
    return decls


def parse_css(css: str, start_order: int = 0) -> tuple[list[Rule], dict[str, str]]:
    """Return (rules, custom_properties_from_:root)."""
    rules: list[Rule] = []
    root_vars: dict[str, str] = {}
    order = start_order
    for head, body, media in _split_top_level(css):
        decls = _parse_decls(body)
        if not decls:
            continue
        for sel in head.split(","):
            sel = sel.strip()
            if not sel:
                continue
            if sel in (":root", "html:root", "*, :root"):
                for k, v in decls.items():
                    if k.startswith("--"):
                        root_vars[k] = v
                continue
            state = "default"
            for pseudo, name in STATE_PSEUDOS.items():
                if sel.endswith(pseudo) or f"{pseudo} " in sel:
                    state = name
                    sel = sel.replace(pseudo, "")
                    break
            sel = re.sub(r"::[a-z-]+", "", sel).strip()
            if not sel:
                continue
            rules.append(Rule(sel, decls, order, media, state))
            order += 1
    return rules, root_vars


# ---------------------------------------------------------------------------
# Selector matching + specificity
# ---------------------------------------------------------------------------
_SIMPLE = re.compile(r"(?:^|(?<=[\s>+~]))([a-zA-Z][\w-]*)?((?:[.#][\w-]+)*)(?:\[[^\]]*\])*")


def _parse_simple(token: str) -> tuple[Optional[str], list[str], Optional[str]]:
    tag = None
    classes: list[str] = []
    el_id = None
    m = re.match(r"^([a-zA-Z][\w-]*|\*)?", token)
    if m and m.group(1) and m.group(1) != "*":
        tag = m.group(1).lower()
    for cm in re.finditer(r"\.([\w-]+)", token):
        classes.append(cm.group(1))
    im = re.search(r"#([\w-]+)", token)
    if im:
        el_id = im.group(1)
    return tag, classes, el_id


def _matches_simple(el: Element, token: str) -> bool:
    tag, classes, el_id = _parse_simple(token)
    if tag and el.tag != tag:
        return False
    if el_id and el.el_id != el_id:
        return False
    have = set(el.classes)
    return all(c in have for c in classes)


def specificity(selector: str) -> tuple[int, int, int]:
    ids = len(re.findall(r"#[\w-]+", selector))
    cls = len(re.findall(r"\.[\w-]+", selector)) + len(re.findall(r"\[[^\]]*\]", selector))
    tags = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][\w-]*)", selector))
    return ids, cls, tags


def matches(el: Element, selector: str) -> bool:
    """Supports descendant (space) and child (>) combinators."""
    tokens = [t for t in re.split(r"\s*(>)\s*|\s+", selector.strip()) if t]
    if not tokens:
        return False
    cur: Optional[Element] = el
    i = len(tokens) - 1
    if not _matches_simple(cur, tokens[i]):
        return False
    i -= 1
    while i >= 0:
        tok = tokens[i]
        if tok == ">":
            i -= 1
            if i < 0:
                return False
            cur = cur.parent
            if cur is None or not _matches_simple(cur, tokens[i]):
                return False
            i -= 1
            continue
        anc = cur.parent
        found = False
        while anc is not None:
            if _matches_simple(anc, tok):
                cur, found = anc, True
                break
            anc = anc.parent
        if not found:
            return False
        i -= 1
    return True


# ---------------------------------------------------------------------------
# var() + shorthands
# ---------------------------------------------------------------------------
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)")


def resolve_vars(value: str, variables: dict[str, str], depth: int = 0) -> str:
    if depth > 12 or "var(" not in value:
        return value

    def sub(m: re.Match) -> str:
        name, fallback = m.group(1), m.group(2)
        if name in variables:
            return resolve_vars(variables[name].strip(), variables, depth + 1)
        return resolve_vars((fallback or "").strip(), variables, depth + 1)

    return _VAR.sub(sub, value)


def _split_values(value: str) -> list[str]:
    """Split on whitespace but keep function calls intact."""
    out, buf, depth = [], "", 0
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if buf:
                out.append(buf)
                buf = ""
            continue
        buf += ch
    if buf:
        out.append(buf)
    return out


def expand_shorthand(prop: str, value: str) -> dict[str, str]:
    """Expand the shorthands that carry design-system meaning."""
    v = _split_values(value)
    if prop in ("padding", "margin"):
        sides = _box_sides(v)
        return {f"{prop}-{k}": val for k, val in sides.items()}
    if prop == "border-radius":
        if len(v) == 1:
            return {"border-radius": v[0]}
        return {"border-radius": v[0]}
    if prop == "border":
        out: dict[str, str] = {}
        for part in v:
            if re.match(r"^-?[\d.]+(px|rem|em|pt)?$", part):
                out["border-width"] = part
            elif part in ("solid", "dashed", "dotted", "none", "double"):
                out["border-style"] = part
            else:
                out["border-color"] = part
        return out
    if prop == "outline":
        out = {}
        for part in v:
            if re.match(r"^-?[\d.]+(px|rem|em|pt)?$", part):
                out["outline-width"] = part
            elif part in ("solid", "dashed", "dotted", "none", "auto"):
                out["outline-style"] = part
            else:
                out["outline-color"] = part
        return out
    if prop == "gap":
        if len(v) == 1:
            return {"gap": v[0], "row-gap": v[0], "column-gap": v[0]}
        return {"row-gap": v[0], "column-gap": v[1], "gap": v[0]}
    if prop == "background" and len(v) == 1:
        return {"background-color": v[0]}
    return {prop: value}


def _box_sides(v: list[str]) -> dict[str, str]:
    if len(v) == 1:
        return {"top": v[0], "right": v[0], "bottom": v[0], "left": v[0]}
    if len(v) == 2:
        return {"top": v[0], "right": v[1], "bottom": v[0], "left": v[1]}
    if len(v) == 3:
        return {"top": v[0], "right": v[1], "bottom": v[2], "left": v[1]}
    return {"top": v[0], "right": v[1], "bottom": v[2], "left": v[3]}


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------
def apply_cascade(
    root: Element,
    rules: list[Rule],
    variables: dict[str, str],
    root_font_size: float = 16.0,
) -> None:
    """Resolve computed styles onto every element, plus per-state overlays."""
    states = ["default"] + sorted({r.state for r in rules if r.state != "default"})

    def resolve_for(el: Element, state: str) -> dict[str, str]:
        matched: list[tuple[tuple[int, int, int], int, dict[str, str]]] = []
        for rule in rules:
            if rule.state not in ("default", state):
                continue
            if rule.media:  # base viewport only; media variants are a separate audit
                continue
            if matches(el, rule.selector):
                matched.append((specificity(rule.selector), rule.order, rule.decls))
        matched.sort(key=lambda t: (t[0], t[1]))

        out: dict[str, str] = {}
        for _, _, decls in matched:
            for prop, raw in decls.items():
                if prop.startswith("--"):
                    continue
                val = resolve_vars(raw, variables)
                out.update(expand_shorthand(prop, val))

        inline = el.attrs.get("style")
        if inline:
            for prop, raw in _parse_decls(inline).items():
                out.update(expand_shorthand(prop, resolve_vars(raw, variables)))
        return out

    def descend(el: Element, inherited: dict[str, str], state: str) -> None:
        own = resolve_for(el, state)
        merged = dict(inherited)
        merged.update(own)

        parent_fs = to_px(inherited.get("font-size"), root_font_size) or root_font_size
        if "font-size" in own:
            own_fs = to_px(own["font-size"], root_font_size, parent_fs)
            if own_fs is not None:
                merged["font-size"] = f"{own_fs}px"
        else:
            merged["font-size"] = f"{parent_fs}px"

        if state == "default":
            el.computed = merged
        else:
            el.computed_states[state] = merged

        pass_down = {k: v for k, v in merged.items() if k in INHERITED}
        for child in el.children:
            descend(child, pass_down, state)

    base_inherit = {"font-size": f"{root_font_size}px", "color": "#000000",
                    "font-family": "sans-serif", "line-height": "normal"}
    for st in states:
        descend(root, dict(base_inherit), st)


def resolve_backgrounds(root: Element) -> None:
    """Walk down carrying the nearest non-transparent background."""
    def descend(el: Element, bg: str) -> None:
        own = el.computed.get("background-color")
        current = bg
        if own and own.lower() not in ("transparent", "none", "inherit"):
            current = own
        el.computed["-dl-effective-background"] = current
        for c in el.children:
            descend(c, current)

    descend(root, "#ffffff")
