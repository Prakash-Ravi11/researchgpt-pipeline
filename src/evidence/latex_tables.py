"""Structural cell model for LaTeX tabular environments — Stage 2, stdlib only.

For EVERY data cell we keep: the value, its column header, its row label, the
table caption, and the enclosing \\section. A flat text dump of the table is NOT
produced here — that is exactly the bindability loss this phase exists to fix.

\\multicolumn / \\multirow are handled where the shape is unambiguous; where a
macro or nesting defeats the parser the whole table is marked
``parse_status="fallback_pdf"`` with a reason, and the caller falls back to the
PDF representation FOR THAT TABLE (see represent.blocks_from_latex). Partial
success per paper is fine; silent failure is not.
"""
from __future__ import annotations

import re
from typing import Any

from .schema import structured_table, table_cell

# --- brace-balanced helpers ------------------------------------------------

def _match_brace(s: str, open_idx: int) -> int:
    """Index of the '}' matching the '{' at open_idx, or -1."""
    depth = 0
    i = open_idx
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _arg_after(s: str, cmd_end: int) -> tuple[str, int]:
    """Read one {..} group starting at/after cmd_end. Returns (inner, index_after)."""
    j = cmd_end
    while j < len(s) and s[j] in " \t\r\n":
        j += 1
    if j >= len(s) or s[j] != "{":
        return "", cmd_end
    k = _match_brace(s, j)
    if k < 0:
        return "", cmd_end
    return s[j + 1:k], k + 1


# --- environment extraction ---------------------------------------------------

_FLOAT_RE = re.compile(r"\\begin\{(table\*?|sidewaystable)\}(.*?)\\end\{\1\}", re.S)
_TABULAR_RE = re.compile(
    r"\\begin\{(tabular\*?|tabularx|array|longtable)\}"
    r"(?:\s*\{[^{}]*\}|\s*\[[^\]]*\])*"      # optional width arg + optional pos arg
    r"\s*\{(?P<colspec>(?:[^{}]|\{[^{}]*\})*)\}"  # the column spec {lcr|p{..}}
    r"(?P<body>.*?)\\end\{\1\}", re.S)
_CAPTION_RE = re.compile(r"\\caption\*?\s*(?:\[[^\]]*\])?\s*\{")
_LABEL_RE = re.compile(r"\\label\s*\{[^{}]*\}")

_SECTION_RE = re.compile(r"\\(?:sub){0,2}section\*?\s*(?:\[[^\]]*\])?\s*\{")

_DROP_MACROS = re.compile(
    r"\\(?:hline|toprule|midrule|bottomrule|cmidrule|addlinespace|centering|small|footnotesize|"
    r"scriptsize|tiny|normalsize|arraybackslash|rowcolor|cellcolor|rule|noalign|kern|vspace|hspace|"
    r"resizebox|scalebox|renewcommand|setlength|def|boldmath|bfseries|itshape|"
    r"cline|specialrule|morecmidrules|belowrulesep|aboverulesep)"
    r"(?:\s*\{[^{}]*\}|\s*\[[^\]]*\]|\s*\*|\d+(?:\.\d+)?[a-z]{0,3})*", re.I)
_TEXT_WRAP = re.compile(
    r"\\(?:textbf|textit|texttt|textrm|textsc|emph|mathrm|mathbf|mathit|text|"
    r"boldsymbol|underline|ensuremath|num|si|SI|numprint)\s*\{")
_SIMPLE_SUBS = [
    (re.compile(r"\\%"), "%"), (re.compile(r"\\&"), "&"), (re.compile(r"\\\$"), "$"),
    (re.compile(r"\\#"), "#"), (re.compile(r"\\_"), "_"),
    (re.compile(r"~"), " "), (re.compile(r"\\,"), " "), (re.compile(r"\\;"), " "),
    (re.compile(r"\\ "), " "), (re.compile(r"\\@"), ""), (re.compile(r"\$"), ""),
    (re.compile(r"\{|\}"), ""), (re.compile(r"\s+"), " "),
]


def _clean(cell: str) -> str:
    """Strip formatting macros/braces from a cell, keep the value + words."""
    prev = None
    s = cell
    # unwrap \textbf{...} etc. repeatedly (may nest)
    while prev != s:
        prev = s
        m = _TEXT_WRAP.search(s)
        if not m:
            break
        close = _match_brace(s, m.end() - 1)
        if close < 0:
            break
        s = s[:m.start()] + s[m.end():close] + s[close + 1:]
    s = _DROP_MACROS.sub(" ", s)
    s = _LABEL_RE.sub("", s)
    for rx, rep in _SIMPLE_SUBS:
        s = rx.sub(rep, s)
    return s.strip(" \t\r\n-|")


# macros that WRAP a numeric argument we must keep verbatim: \num{88.5}, \SI{88.5}{\%},
# \numprint{1000}, \nicefrac{1}{2}, \sfrac{3}{4}, \ang{45}
_NUM_WRAP = re.compile(r"\\(?:num|numprint|SI|si|ang|nicefrac|sfrac|slashfrac)\s*\{")
_MATH_OPS = re.compile(r"\\(?:pm|mp|times|cdot|div|leq|geq|approx|sim|to|rightarrow|"
                       r"pm\b|percent|%|circ|degree|micro|mu|alpha|beta|gamma|delta|"
                       r"lambda|sigma|rho|infty|pm)\b")


def _numeric_verbatim(s: str) -> str:
    """Linearise a chunk of tabular LaTeX WITHOUT losing a single numeric token.
    Keeps $...$ contents, \\num{}/\\SI{} bodies, x\\pm y, sub/superscripts, units.
    Only structural noise (rules, & \\\\ separators, wrapper macros) is removed."""
    # unwrap \num{...}/\SI{...}{...}/\textbf{...} etc — keep the inner text
    for wrap in (_NUM_WRAP, _TEXT_WRAP):
        prev = None
        while prev != s:
            prev = s
            m = wrap.search(s)
            if not m:
                break
            close = _match_brace(s, m.end() - 1)
            if close < 0:
                break
            s = s[:m.start()] + " " + s[m.end():close] + " " + s[close + 1:]
    # \multicolumn{n}{spec}{X} / \multirow{n}{w}{X} -> keep X
    for mac in (r"\\multicolumn", r"\\multirow"):
        while True:
            m = re.search(mac + r"\s*\{", s)
            if not m:
                break
            a = _match_brace(s, m.end() - 1)
            b = _match_brace(s, a + 1) if a >= 0 and a + 1 < len(s) and s[a + 1] == "{" else -1
            c = _match_brace(s, b + 1) if b >= 0 and b + 1 < len(s) and s[b + 1] == "{" else -1
            if c < 0:
                s = s[:m.start()] + " " + s[m.end():]
                break
            s = s[:m.start()] + " " + s[b + 1:c] + " " + s[c + 1:]
    s = _DROP_MACROS.sub(" ", s)
    s = _LABEL_RE.sub("", s)
    s = _MATH_OPS.sub(" ", s)
    s = re.sub(r"(?<!\\)&", " | ", s)          # column separator
    s = re.sub(r"\\\\(?:\s*\[[^\]]*\])?", "  ", s)  # row separator
    s = re.sub(r"\\[a-zA-Z@]+\*?", " ", s)     # any remaining command name (args kept)
    s = re.sub(r"[\$\{\}~^_]", " ", s)
    s = s.replace(r"\%", "%").replace(r"\&", "&").replace(r"\_", "_")
    return re.sub(r"\s+", " ", s).strip(" |-")


def _tabular_raw_text(env_body: str) -> str:
    return _numeric_verbatim(re.sub(r"(?<!\\)%.*", "", env_body))


# --- nested grid detection (EXP-LATEX-01) -------------------------------------

#: Environments that carry their own `&` / `\\` grid. One of these opening inside
#: a tabular body means the row/column split below is not trustworthy. Nesting is
#: tracked across the whole family, not per environment name, because
#: `array` inside `tabular` corrupts the row split just as `tabular` does.
_GRID_ENVS = ("tabular\\*", "tabular", "tabularx", "array", "longtable")
_GRID_ALT = "|".join(_GRID_ENVS)

_ANY_GRID_BEGIN = re.compile(r"\\begin\s*\{(?:" + _GRID_ALT + r")\}")
_ANY_GRID_END = re.compile(r"\\end\s*\{(?:" + _GRID_ALT + r")\}")


def _true_env_body(s: str, body_start: int) -> tuple[str, int, int]:
    """Body of the grid environment opened before `body_start`, nesting-aware.

    ``_TABULAR_RE`` is non-greedy and keys its closer on the SAME environment
    name, so ``\\begin{tabular} ... \\begin{tabular} ... \\end{tabular} ...
    \\end{tabular}`` makes it stop at the INNER ``\\end`` — the tail of the outer
    table (whole rows, and their numbers) is then invisible to both the cell
    parser and ``raw_text``. This walks begin/end pairs across the whole grid
    family and returns the body up to the *matching* closer.

    Returns ``(body, end_index, n_nested_opens)``. ``n_nested_opens`` > 0 means a
    grid environment opened inside this one; the caller must not trust a plain
    ``&``/``\\\\`` split of the result.
    """
    depth = 1
    nested = 0
    i = body_start
    n = len(s)
    while i < n:
        mb = _ANY_GRID_BEGIN.search(s, i)
        me = _ANY_GRID_END.search(s, i)
        if me is None:
            break                                   # unterminated — caller falls back
        if mb is not None and mb.start() < me.start():
            depth += 1
            nested += 1
            i = mb.end()
            continue
        depth -= 1
        if depth == 0:
            return s[body_start:me.start()], me.end(), nested
        i = me.end()
    return s[body_start:], n, nested


def _split_top(s: str, sep: str) -> list[str]:
    """Split on `sep` at brace depth 0, honouring \\escapes."""
    out, buf, depth, i = [], [], 0, 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            buf.append(s[i:i + 2]); i += 2; continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        if depth == 0 and s.startswith(sep, i):
            out.append("".join(buf)); buf = []; i += len(sep); continue
        buf.append(c); i += 1
    out.append("".join(buf))
    return out


_ROWSEP = re.compile(r"\\\\(?:\s*\[[^\]]*\])?")


def _rows(body: str) -> list[str]:
    body = re.sub(r"(?<!\\)%.*", "", body)          # strip line comments
    parts = _ROWSEP.split(body)
    return [p for p in (x.strip() for x in parts) if p and not re.fullmatch(r"[\\\s]*", p)]


def _expand_cells(row: str) -> tuple[list[str], list[dict[str, int]], bool]:
    """row -> (cell_texts, per-cell span dict, ok). Expands \\multicolumn; records
    \\multirow. Returns ok=False if a span macro can't be read."""
    raw_cells = _split_top(row, "&")
    texts: list[str] = []
    spans: list[dict[str, int]] = []
    ok = True
    for rc in raw_cells:
        mc = re.search(r"\\multicolumn\s*\{", rc)
        mr = re.search(r"\\multirow\s*\{", rc)
        if mc:
            n_str, after = _arg_after(rc, mc.end() - 1)
            _spec, after = _arg_after(rc, after)
            inner, _ = _arg_after(rc, after)
            try:
                n = int(n_str.strip())
            except ValueError:
                ok = False
                n = 1
            texts.append(_clean(inner))
            spans.append({"colspan": n})
            for _ in range(n - 1):
                texts.append("")
                spans.append({"colspan": 0})       # 0 => absorbed by the preceding span
        elif mr:
            n_str, after = _arg_after(rc, mr.end() - 1)
            _w, after = _arg_after(rc, after)
            inner, _ = _arg_after(rc, after)
            try:
                n = int(n_str.strip())
            except ValueError:
                ok = False
                n = 1
            texts.append(_clean(inner))
            spans.append({"rowspan": n})
        else:
            texts.append(_clean(rc))
            spans.append({})
    return texts, spans, ok


def _n_columns(colspec: str) -> int:
    # count l/c/r/p{}/m{}/b{}/X columns, ignore | @{} > < ! and whitespace
    spec = re.sub(r"@\{[^{}]*\}|>\{[^{}]*\}|<\{[^{}]*\}|!\{[^{}]*\}", "", colspec)
    spec = re.sub(r"[pmb]\{[^{}]*\}", "P", spec)
    spec = re.sub(r"\*\{(\d+)\}\{([^{}]*)\}",
                  lambda m: ("P" if "p" in m.group(2) else m.group(2).strip("|@ ")) * int(m.group(1)),
                  spec)
    return len(re.findall(r"[lcrPXY]", spec))


def _sections_by_pos(latex: str) -> list[tuple[int, str]]:
    out = [(0, "body")]
    for m in _SECTION_RE.finditer(latex):
        inner, _ = _arg_after(latex, m.end() - 1)
        title = _clean(inner) or "body"
        out.append((m.start(), title))
    return out


def _section_at(pos: int, secmap: list[tuple[int, str]]) -> str:
    cur = "body"
    for p, name in secmap:
        if p <= pos:
            cur = name
        else:
            break
    return cur


def _caption_in(float_body: str) -> str:
    m = _CAPTION_RE.search(float_body)
    if not m:
        return ""
    inner, _ = _arg_after(float_body, m.end() - 1)
    return _clean(inner)


def parse_latex_tables(latex: str, paper_id: str, source: str) -> list[dict[str, Any]]:
    """All table floats in `latex` as canonical structured_table dicts."""
    secmap = _sections_by_pos(latex)
    tables: list[dict[str, Any]] = []
    seen_spans: list[tuple[int, int]] = []
    idx = 0

    def emit_from(env_body: str, colspec: str, caption: str, section: str, tid: str,
                  nested: int = 0) -> dict[str, Any]:
        notes: list[str] = []
        raw = _tabular_raw_text(env_body)     # PARITY: full verbatim cell content, always
        if nested:
            # A grid environment opened inside this one. `&` and `\\` now belong
            # to two different tables, so any row/column split here would invent
            # structure — the pre-EXP-LATEX-01 parser did exactly that and
            # reported parse_status="parsed" while dropping the rows after the
            # inner \end{tabular}. Declare the structural failure and ship every
            # value through raw_text, which spans the WHOLE outer environment.
            return structured_table(
                table_id=tid, paper_id=paper_id, source=source,
                representation="latex", section=section, caption=caption,
                cells=[], parse_status="fallback_pdf", raw_text=raw,
                fallback="nested_tabular",
                notes=[f"{nested} nested grid environment(s); "
                       f"structural split refused, raw_text carries all values"])
        try:
            rows = _rows(env_body)
        except Exception as exc:  # noqa: BLE001
            return structured_table(table_id=tid, paper_id=paper_id, source=source,
                                    representation="latex", section=section, caption=caption,
                                    cells=[], parse_status="fallback_pdf", raw_text=raw,
                                    fallback=f"row_split_error:{type(exc).__name__}")
        if len(rows) < 2:
            return structured_table(table_id=tid, paper_id=paper_id, source=source,
                                    representation="latex", section=section, caption=caption,
                                    cells=[], parse_status="fallback_pdf", raw_text=raw,
                                    fallback=f"too_few_rows:{len(rows)}")
        ncol = _n_columns(colspec) or len(_split_top(rows[0], "&"))
        header_texts, _hs, hok = _expand_cells(rows[0])
        if not hok:
            notes.append("multicol/multirow arg unreadable in header")
        # pad/truncate header to ncol
        header = (header_texts + [""] * ncol)[:ncol]
        cells: list[dict[str, Any]] = []
        span_trouble = 0
        for r_i, row in enumerate(rows[1:], start=1):
            texts, spans, rok = _expand_cells(row)
            if not rok:
                span_trouble += 1
            row_label = texts[0].strip() if texts else ""
            col_cursor = 0
            for c_i, (val, sp) in enumerate(zip(texts, spans)):
                if sp.get("colspan") == 0:
                    col_cursor += 1
                    continue
                colspan = sp.get("colspan", 1) or 1
                head = header[col_cursor] if col_cursor < len(header) else ""
                if not val or c_i == 0:
                    col_cursor += colspan
                    continue
                cells.append(table_cell(
                    value=val, column_header=head, row_label=row_label,
                    caption=caption, section=section, row=r_i, col=col_cursor,
                    spans={k: v for k, v in sp.items() if v and v != 1}))
                col_cursor += colspan
        status = "parsed"
        fb = None
        if span_trouble:
            notes.append(f"{span_trouble} row(s) with unreadable span macro")
            status = "partial"
        if not cells:
            # no clean structured cells — but the values still ship via raw_text
            status, fb = "fallback_pdf", "no_data_cells_after_parse"
        elif len(cells) < sum(1 for r in rows[1:] for _ in _split_top(r, "&")) * 0.5:
            notes.append("under half the cells parsed structurally; raw_text carries the rest")
            status = "partial" if status == "parsed" else status
        return structured_table(table_id=tid, paper_id=paper_id, source=source,
                                representation="latex", section=section, caption=caption,
                                cells=cells, parse_status=status, fallback=fb, notes=notes,
                                raw_text=raw)

    # 1) table floats
    for fm in _FLOAT_RE.finditer(latex):
        idx += 1
        fbody = fm.group(2)
        section = _section_at(fm.start(), secmap)
        caption = _caption_in(fbody)
        tm = _TABULAR_RE.search(fbody)
        tid = f"{paper_id}:tab{idx}"
        if not tm:
            # image-only "table" (\includegraphics) — no tabular grid, but keep any
            # in-float text (sometimes a table is typeset as inline numbers).
            body_wo_cap = _CAPTION_RE.sub(" ", fbody)
            tables.append(structured_table(
                table_id=tid, paper_id=paper_id, source=source, representation="latex",
                section=section, caption=caption, cells=[], parse_status="fallback_pdf",
                fallback="no_tabular_env_in_float",
                raw_text=_numeric_verbatim(body_wo_cap)))
            continue
        body, body_end, nested = _true_env_body(fbody, tm.start("body"))
        seen_spans.append((fm.start() + tm.start(), fm.start() + body_end))
        tables.append(emit_from(body, tm.group("colspec"), caption, section, tid, nested))

    # 2) bare tabular/longtable not inside a float
    for tm in _TABULAR_RE.finditer(latex):
        if any(a <= tm.start() < b for a, b in seen_spans):
            continue
        idx += 1
        section = _section_at(tm.start(), secmap)
        tid = f"{paper_id}:tab{idx}"
        body, body_end, nested = _true_env_body(latex, tm.start("body"))
        seen_spans.append((tm.start(), body_end))
        tables.append(emit_from(body, tm.group("colspec"), "", section, tid, nested))

    return tables
