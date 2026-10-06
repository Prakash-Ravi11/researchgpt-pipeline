"""Binder v2 (phase 10): deterministic claim-to-cell binding, routed from gate.py by `binder_policy`.

    ClaimFrame -> value-matching candidates -> per-cell links and conflicts -> eligibility -> dominance choice or an
    ambiguity abstention -> an independent deterministic verifier -> BIND / ABSTAIN.
    v2_llm adds a judge for 2-5 undominated cells or an unresolved alias. Its answer must pass the same verifier.

Precision first: a cell binds only when everything the claim names around the value agrees with that cell.
- subject: a label of the cell (its row label or a column-header level) or an alias (own method, declared name,
  group noun), named where the value's subject is. That is the clause before its first value without comparator
  phrases, or the value's own "for/by" phrase, parenthesis head or local words. A comparator value (the right side
  of "vs", "than" or "outperforms") takes the comparator's.
- quantity: a quantity term named for the value (its local words, then the clause prefix, then the clause). It
  must be the cell's leaf header, row label, part label, caption metric or count header. No other quantity term
  may be named.
- no conflict:
  - no other label of the same table on the subject axis, unless that label holds the same value (ambiguity);
  - no other label on a qualifier axis;
  - no unexplained name in the value's qualifier phrases;
  - no own-method reference for a non-own cell;
  - no disagreement on the unit or on "Table N".
Definitions: src/evaluation/binder_10/PREREG_10.md. PHASE10_REPORT.md lists the deviations fixed before any
measurement. There is no claim id, paper id or evaluation string here. RGPT_BINDER_V2_DISABLE (comma-separated
MECHANISMS) switches one mechanism off for the ablations.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from . import gate as G
from .borderless import norm

MECHANISMS = ("caption_quantity", "column_subject", "own_alias", "synonyms", "count_attribute",
              "multi_binding", "table_mention", "gate_fixes")
SINGLE, MULTI, COMPARISON, PARTIAL = "SINGLE_CELL", "MULTI_CELL", "COMPARISON", "PARTIAL_COMPARISON"
TRACE_CAP = 50                      # candidate cells listed per value in v2_trace (the count is always kept)
_CACHE: dict[Any, dict] = {}        # paper index per (content key, disabled mechanisms)


class LLMViolation(RuntimeError):
    """The judge answered with an id or a span that is not in its input: a phase STOP (PREREG E)."""


def _off() -> frozenset[str]:
    return frozenset(x.strip() for x in os.environ.get("RGPT_BINDER_V2_DISABLE", "").split(",") if x.strip())


# --- vocabulary: general, written down (PREREG D2/D5 and the deviations in PHASE10_REPORT.md) ---------------------
_FUNCTION = frozenset("""a an and are as at be been being both but by can could did do does each either for from had
has have here how however i if in into is it its may might more most much no nor not of on or our over per so such
than that the their them then there these they this those thus to too under up us very via was we were what when
where whereas which while who whom will with within without would also all any another""".split())
_GENERIC = frozenset("""method methods model models approach approaches network networks framework frameworks system
systems pipeline pipelines module modules technique techniques algorithm algorithms architecture architectures result
results performance score scores value values set sets dataset datasets data""".split())
_STAT = frozenset("ci sd se sem iqr df".split())
_GROUP_NOUNS = ("controls", "patients", "subjects", "participants", "cases", "volunteers", "fetuses", "infants",
                "neonates", "children", "adults", "women", "men", "mothers", "pregnancies", "cohorts")
_SYN_PHRASE = re.compile(r"\bdice(?:[\s-]+similarity)?(?:[\s-]+(?:coefficient|score|index))?s?\b|\bdscs?\b", re.I)
_OWN_NOUNS = r"(?:method|model|approach|network|framework|system|pipeline|module|technique|algorithm|architecture)s?"
_OWN_REF = re.compile(r"\bour(?:\s+(?:proposed|full|complete|final))?\s+" + _OWN_NOUNS + r"\b|\bthe\s+proposed\s+"
                      + _OWN_NOUNS + r"\b|\bours\b", re.I)
_OWN_MARK = re.compile(r"\b(?:ours|proposed)\b", re.I)
_VARIANT = re.compile(r"\bw/o\b|\bw/|\bwithout\b|\bwith\b|\bno\b|\bonly\b|\bablat|^\s*[-+]", re.I)
_VERB = re.compile(r"\b(?:reports?|achiev\w*|obtain\w*|attain\w*|reach\w*|record\w*|gets?|scor\w*|yield\w*|produc\w*|"
                   r"show\w*|deliver\w*|perform\w*|gives?|has|had|have|is|are|was|were)\b", re.I)
_PASSIVE_BY = re.compile(r"\b(?:obtained|achieved|reached|attained|reported|yielded|produced|scored|recorded)\s+by\s+",
                         re.I)
_UNIT = r"(?:%|mm[23²³]?|cm[23²³]?|millimet(?:er|re)s?|centimet(?:er|re)s?|ml|ms|min|s|weeks?|days?|years?|kg|t)"
_UNIT_AFTER = re.compile(r"^ ?(" + _UNIT + r")(?![A-Za-z0-9])", re.I)
_UNIT_IN_LABEL = re.compile(r"[\(\[,]\s*(" + _UNIT + r")\s*[\)\]]", re.I)
_UNIT_IN_VALUE = re.compile(r"(?<=\d)\s?(" + _UNIT + r")(?![A-Za-z0-9])", re.I)
_NOT_COUNT = frozenset("weeks days years months hours minutes seconds points percent percentage times folds".split())
_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

# --- text and tokens -----------------------------------------------------------------------------------------------
_LIGATURES = (("ﬀ", "ff"), ("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬃ", "ffi"), ("ﬄ", "ffl"))
_ODD_SPACE = re.compile(r"[  -​  　\x00]")
_LEAD_DASH = re.compile(r"(?<![^\s(\[=:])[–—](?=\d)")
_TOKEN = re.compile(r"[^\W_]+(?:\+\+|\+)?")
_BRACKET = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_SEP = re.compile(r"[\s\-_/.@]*")  # retain every token in ranked metrics such as Gain@k


def _prep(s: Any) -> str:
    """Working text: ligatures expanded, U+2212 (and a dash before a digit after a space) as '-', soft hyphens
    dropped, every whitespace run as one space."""
    s = "" if s is None else str(s)
    for a, b in _LIGATURES:
        s = s.replace(a, b)
    s = _LEAD_DASH.sub("-", _ODD_SPACE.sub(" ", s.replace("−", "-").replace("­", "")))
    return " ".join(s.split())


def _canon(tok: str, syn: bool) -> str:
    t = tok.lower()
    if not syn:
        return t
    t = t.translate(_SUPER)
    if t in ("dsc", "dscs"):
        return "dice"
    if (len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")) and t not in _FUNCTION
            and t[:-1] not in _FUNCTION):
        t = t[:-1]
    return t


def _tokens(text: str, syn: bool) -> list[tuple[str, str, int, int]]:
    """(original, canonical, start, end) of the word tokens of `text`. A synonym phrase (D5) is one token, 'dice'."""
    spans = [m.span() for m in _SYN_PHRASE.finditer(text)] if syn else []
    out: list[tuple[str, str, int, int]] = []
    si = 0
    for m in _TOKEN.finditer(text):
        s, e = m.span()
        while si < len(spans) and spans[si][1] <= s:
            si += 1
        if si < len(spans) and spans[si][0] <= s:
            a, b = spans[si]
            if not (out and out[-1][2] == a):
                out.append((text[a:b], "dice", a, b))
            continue
        out.append((m.group(0), _canon(m.group(0), syn), s, e))
    return out


def _core(label: Any) -> str:
    return _prep(_BRACKET.sub(" ", _prep(label)))


def _bracket(label: Any) -> str:
    return " ".join(x[1:-1].strip() for x in _BRACKET.findall(_prep(label)))


def _own_label(label: str) -> bool:
    core = _core(label)
    decorated = any(_OWN_MARK.fullmatch(x[1:-1].strip()) for x in _BRACKET.findall(_prep(label)))
    return bool(not _VARIANT.search(label) and (decorated or _OWN_MARK.search(core) or _OWN_REF.fullmatch(core)))


def _form(text: Any, syn: bool) -> str:
    return "".join(t[1] for t in _tokens(_prep(text), syn))


def _flat(s: Any) -> str:
    """The verifier's own reading: lower-case alphanumerics and '+', synonym phrases as 'dice', a word's final 's'
    dropped."""
    s = _SYN_PHRASE.sub(" dice ", _prep(s).translate(_SUPER).lower())
    return "".join(re.sub(r"(?<=[a-z]{3})s$", "", w) for w in re.findall(r"[a-z0-9+]+", s))


def _named(tok: str) -> bool:
    """A name-like token: an upper-case letter after the first character, or letters mixed with digits."""
    letters = sum(ch.isalpha() for ch in tok)
    return (letters >= 2 and any(ch.isupper() for ch in tok[1:])) or (letters >= 1 and any(ch.isdigit() for ch in tok))


# --- numbers -------------------------------------------------------------------------------------------------------
_N = r"-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
_NUMBER = re.compile(r"(?<![\w.])(?<![A-Za-z]-)(-)?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?!\d|\.\d)",
                     re.ASCII)
_YEAR = re.compile(r"(?:19|20)\d{2}")
_REF_BEFORE = re.compile(r"(?:\btables?|\btab\.|\bfig(?:ure)?s?\.?|\bsec(?:tion)?s?\.?|\beq(?:uation)?s?\.?|\bappendix|"
                         r"\bsupplementary|\brefs?\.?|§)\s*\(?\s*(?:[\dIVX]+\s*(?:,|and|&|to|-|–)\s*)*$", re.I)
_THRESHOLD = re.compile(r"(?:\bexceed\w*|\babove|\bover|\bat least|\bat most|\bmore than|\bgreater than|\bhigher than|"
                        r"\blower than|\bless than|\bfewer than|\bbelow|\bunder|\bup to|\bbeyond|[<>≤≥]=?)"
                        r"\s*(?:a |an |the )?$", re.I)
_DELTA = re.compile(r"(?:\b(?:improv|increas|decreas|reduc|gain|boost|drop|declin|outperform|surpass|exceed|rais|"
                    r"lower|lead|higher|better|worse)\w*\b[^.;,()]{0,40}?\bby|\b(?:improvement|increase|decrease|"
                    r"reduction|gain|boost|drop|decline|difference|margin|change)s?\s+(?:of|by)|(?<![\w+])\+|"
                    r"Δ\s*=?)\s*$", re.I)
_PM = re.compile(r"^ ?(?:±|\+/-|\+-) ?(\d+(?:\.\d+)?)", re.A)
_INTERVAL = re.compile(r"^ ?[\(\[] ?(?:\d+ ?% ?(?:CI|confidence interval)\b ?[,:=]? ?)?(-?\d+(?:\.\d+)?) ?"
                       r"(?:,|;|–|—|-|to) ?(-?\d+(?:\.\d+)?) ?[\)\]]", re.I | re.A)
_RANGE = re.compile(r"^(?:[–—-]| [–—-] )(\d+(?:\.\d+)?)(?![\d.])", re.A)
_COUNT_NOUN = re.compile(r"^ ?(?:[A-Za-z][\w-]* ){0,3}?([A-Za-z]{3,}s)\b")


def _num(sign: str | None, digits: str) -> str:
    d = digits.replace(",", "")
    return (sign or "") + ("0" + d if d.startswith(".") else d)


def _n(x: str) -> str:
    return _num("-" if x.startswith("-") else None, x.lstrip("-"))


def _unit(u: str | None) -> str | None:
    if not u:
        return None
    u = u.lower().translate(_SUPER)
    if re.fullmatch(r"millimet(?:er|re)s?", u):
        return "mm"
    if re.fullmatch(r"centimet(?:er|re)s?", u):
        return "cm"
    return {"week": "weeks", "day": "days", "year": "years"}.get(u, u)


def mentions(text: str) -> list[dict[str, Any]]:
    """ClaimFrame values (PREREG D2), in claim order, with their structure."""
    w = text or ""
    out: list[dict[str, Any]] = []
    skip = 0
    for m in _NUMBER.finditer(w):
        s, e = m.span()
        digits = m.group(2).replace(",", "")
        if s < skip or not ("." in digits or len(digits) >= 2):
            continue
        before, rest = w[max(0, s - 48):s], w[e:]
        if (re.match(r"[eE][+-]?\d", rest) or ("." not in digits and _YEAR.fullmatch(digits))
                or re.search(r"\brow\s+$", before, re.I)
                or _REF_BEFORE.search(before) or w.rfind("[", 0, s) > w.rfind("]", 0, s)
                or re.match(r" ?% ?(?:CI\b|confidence)", rest, re.I)):
            continue
        clause_before = re.split(r"[;.!?]\s+", w[:s])[-1]
        rec = {"tok": _num(m.group(1), m.group(2)), "start": s, "end": e, "pm": None, "interval": None,
               "range": None, "unit": None, "count": None, "threshold": bool(_THRESHOLD.search(before)),
               "delta": bool(_DELTA.search(before)),
               "negated": bool(re.search(r"\b(?:not|never|neither|other than)\b", clause_before, re.I))}
        # A central value's unit may precede uncertainty (73.2% +/- 1.4%).
        leading_unit = _UNIT_AFTER.match(rest)
        if leading_unit:
            rec["unit"] = _unit(leading_unit.group(1))
            e += leading_unit.end()
            rest = w[e:]
        wrapper = re.match(r"^\s*\(\s*(?=±|\+/-|\+-)", rest)
        if wrapper:
            e += wrapper.end()
            rest = w[e:]
        pm = _PM.match(rest)
        if pm:
            rec["pm"], e = pm.group(1), e + pm.end()
            rest = w[e:]
            uncertainty_unit = _UNIT_AFTER.match(rest)
            if uncertainty_unit:
                rec["unit"] = rec["unit"] or _unit(uncertainty_unit.group(1))
                e += uncertainty_unit.end()
                rest = w[e:]
            if wrapper and rest.startswith(")"):
                e += 1
                rest = w[e:]
        ci_prefix = re.match(r"^\s*(?:,\s*|with\s+(?:a\s+)?)?(?:\d+(?:\.\d+)?\s*%\s*)?"
                             r"(?:CI\b|confidence interval\b)\s*(?:of\s*)?[:=]?\s*", rest, re.I)
        if ci_prefix:
            e += ci_prefix.end()
            rest = w[e:]
        iv = _INTERVAL.match(rest)
        if iv:
            rec["interval"], e = (_n(iv.group(1)), _n(iv.group(2))), e + iv.end()
            rest = w[e:]
        rd = None if (rec["pm"] or rec["interval"]) else _RANGE.match(rest)
        if rd:
            rec["range"], e = (rec["tok"], _n(rd.group(1))), e + rd.end()
            rest = w[e:]
        elif re.search(r"\bbetween\s+$", before, re.I):
            a = re.match(r"^\s+and\s+(-?\d+(?:\.\d+)?)(?![\d.])", rest)
            if a:
                rec["range"], e = (rec["tok"], _n(a.group(1))), e + a.end()
                rest = w[e:]
        un = _UNIT_AFTER.match(rest)
        rec["unit"] = rec["unit"] or (_unit(un.group(1)) if un else None)
        if "." not in digits and not (rec["range"] or rec["pm"] or rec["interval"] or un):
            cn = _COUNT_NOUN.match(rest)
            if cn and cn.group(1).lower() not in _NOT_COUNT and not re.match(r"^ ?percentage", rest, re.I):
                rec["count"], rec["count_end"] = cn.group(1), e + cn.end()
        if un:
            e += un.end()
        rec["end"] = skip = e
        out.append(rec)
    return out


# --- cells (PREREG D3) ---------------------------------------------------------------------------------------------
_MARKS = r"[*†‡§¶]*"
_PART = re.compile(r"^\s*([A-Za-z][\w\s\-()%²³/.]*?)\s*(?::|=|\s)\s*(" + _N + r")\s*(" + _UNIT + r")?\s*"
                   + _MARKS + r"\s*$", re.I | re.A)
_C_PM = re.compile(r"(" + _N + r")%?(?:±|\+/-|\+-)(" + _N + r")(?:" + _UNIT + r")?" + _MARKS, re.I | re.A)
_C_IV = re.compile(r"(" + _N + r")(?:" + _UNIT + r")?[\(\[](" + _N + r")(?:,|;|–|—|-|to)(" + _N + r")[\)\]]"
                   r"(?:" + _UNIT + r")?" + _MARKS, re.I | re.A)
_C_RANGE = re.compile(r"(" + _N + r")(?:–|—|-|to)(" + _N + r")(?:" + _UNIT + r")?", re.I | re.A)
_C_SECOND = re.compile(r"(" + _N + r")(?:" + _UNIT + r")?[\(\[](?:" + _N + r")%?[\)\]]", re.I | re.A)
_C_PLAIN = re.compile(r"(" + _N + r")(?:" + _UNIT + r")?" + _MARKS, re.I | re.A)
_COUNT_HEADER = re.compile(r"^(?:(?:number|no\.?|num\.?|#)\s*(?:of\s+)?([A-Za-z][A-Za-z -]*?)|([A-Za-z][A-Za-z -]*?)\s*"
                           r"[\(\[](?:n|#|no\.?|count)[\)\]]|(n|#|counts?|no\.?))\s*$", re.I)


def _parse_cell(c: dict[str, Any], syn: bool = True) -> dict[str, Any]:
    value = _prep(c.get("value"))
    header = _prep(c.get("column_header"))
    levels = [x.strip() for x in header.split(" / ")] if header else [""]
    row, cap = _prep(c.get("row_label")), _prep(c.get("caption"))
    p: dict[str, Any] = {"raw": c, "value": value, "row": row, "col": header, "levels": levels, "cap": cap,
                         "central": None, "pm": None, "interval": None, "range": None, "parts": [], "nums": []}
    if re.search(r"[A-Za-z]{2,}", value):                         # text cell: "DSC: 83.79%, VS: 84.84%"
        for seg in (x for x in re.split(r",\s+|;\s*|\s+/\s+", value) if x.strip()):
            pm = _PART.match(seg)
            if pm and re.search(r"[A-Za-z]{2,}", pm.group(1)):
                p["parts"].append((pm.group(1).strip(), _n(pm.group(2)), _unit(pm.group(3))))
        if not p["parts"]:
            p["nums"] = [_num(m.group(1), m.group(2)) for word in value.split(" ") for m in _NUMBER.finditer(norm(word))]
            p["central"] = p["nums"][0] if len(p["nums"]) == 1 else None
    else:
        flat = norm(value)                                         # '0.94 7' -> '0.947'; '0.87 ± 0.06' -> '0.87±0.06'
        p["nums"] = [_num(m.group(1), m.group(2)) for m in _NUMBER.finditer(flat)]
        for rx, kind in ((_C_PM, "pm"), (_C_IV, "iv"), (_C_RANGE, "range"), (_C_SECOND, "second"), (_C_PLAIN, "plain")):
            mm = rx.fullmatch(flat)
            if not mm:
                continue
            if kind == "range":
                p["range"] = (_n(mm.group(1)), _n(mm.group(2)))
            else:
                p["central"] = _n(mm.group(1))
                if kind == "pm":
                    p["pm"] = mm.group(2).lstrip("-")
                elif kind == "iv":
                    p["interval"] = (_n(mm.group(2)), _n(mm.group(3)))
            break
        else:
            if len(p["nums"]) == 1:
                p["central"] = p["nums"][0]
            elif len(p["nums"]) > 1 and "/" in flat:              # '0.81 / 0.70' under 'Dice / IoU' or 'Dice/IoU'
                names = levels if len(levels) == len(p["nums"]) else [x.strip() for x in header.split("/")]
                if len(names) == len(p["nums"]):
                    p["parts"] = [(lab, n, None) for lab, n in zip(names, p["nums"])]
    p["units"] = {_unit(u) for u in _UNIT_IN_VALUE.findall(value)}
    p["label_units"] = {_unit(u) for x in levels + [row] for u in _UNIT_IN_LABEL.findall(x.translate(_SUPER))}
    p["pct"] = "%" in value or any("%" in x for x in levels + [row])
    # Caption units belong to their named quantity, never every column.
    for prefix in cap.split("%")[:-1]:
        scope = re.split(r"[,;]|\band\b", prefix, flags=re.I)[-1]
        if any(_form(_core(lab), syn) and _form(_core(lab), syn) in _form(scope, syn)
               for lab in levels + [row]):
            p["pct"] = True
    if any(re.search(r"\bfraction\b", lab, re.I) for lab in levels + [row]):
        p["pct"] = False
    p["count"] = None
    for lab in (levels[-1], row):
        cm = _COUNT_HEADER.match(_core(lab)) or _COUNT_HEADER.match(lab)
        if cm:
            noun = (cm.group(1) or cm.group(2) or "").split()
            p["count"] = _canon(noun[-1], syn) if noun else ""
            break
    return p


def _value_hits(m: dict[str, Any], p: dict[str, Any]) -> list[int | None]:
    """Where m's value is in p: None for the central value, k for part k; [] if it is not (PREREG D6 value)."""
    if m["range"] or p["range"]:
        return [None] if m["range"] and m["range"] == p["range"] else []
    if p["parts"]:
        return [k for k, part in enumerate(p["parts"]) if part[1] == m["tok"]]
    if p["central"] != m["tok"]:
        return []
    if (m["pm"] and p["pm"] and m["pm"] != p["pm"]) or (m["interval"] and p["interval"] and m["interval"] != p["interval"]):
        return []
    return [None]


def _unit_ok(m: dict[str, Any], p: dict[str, Any], part: int | None) -> bool:
    u = m["unit"]
    if not u:
        return True
    if part is not None and p["parts"][part][2]:
        return p["parts"][part][2] == u                         # "HD95: 35.66 mm" is mm, whatever else the cell holds
    units = set(p["label_units"]) | (set(p["units"]) if part is None else set())
    if u == "%":
        pct = p["pct"] if part is None else any("%" in x for x in p["levels"] + [p["row"], p["parts"][part][0]])
        return pct or "%" in units
    return not units or u in units


# --- the paper index (cached per paper content and disabled mechanisms) -----------------------------------------
_TABLE_LABEL = re.compile(r"^\s*(?i:table|tab\.?)\s*([0-9]+|[IVXLC]+)\b")
_TABLE_REF = re.compile(r"\b(?i:tables?|tab\.)\s*((?:[0-9]+|[IVXLC]+)\b(?:\s*(?:,|and|&|to|-|–)\s*"
                        r"(?:[0-9]+|[IVXLC]+)\b)*)")
_SENT_SPLIT = re.compile(r"(?<=[.!?])(?<!\bvs\.)(?<!\bal\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bFig\.)(?<!\bEq\.)(?<!\bNo\.)"
                         r"\s+(?=[A-Z(\[])")
_DECLARE = re.compile(r"\b[Ww]e\s+(?:(?:also|further|then|here|now|first|additionally|newly|thus|therefore|hence)\s+)?"
                      r"(?:propose|present|introduce|develop|design)d?\s+([A-Z][A-Za-z0-9]*(?:[-+][A-Za-z0-9]+)*\+*)")
_NAMED_AS = re.compile(r"\b(?:called|named|termed|dubbed)\s+([A-Z][A-Za-z0-9]*(?:[-+][A-Za-z0-9]+)*\+*)")


def _tnum(s: str) -> str:
    if s.isdigit():
        return str(int(s))
    val = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = prev = 0
    for ch in reversed(s):
        total, prev = total + (-val[ch] if val[ch] < prev else val[ch]), max(prev, val[ch])
    return str(total)


def _tables_named(w: str) -> set[str]:
    out: set[str] = set()
    for m in _TABLE_REF.finditer(w):
        out.update(_tnum(x) for x in re.findall(r"[0-9]+|[IVXLC]+", m.group(1)))
        for a, b in re.findall(r"([0-9]+)\s*(?:to|-|–)\s*([0-9]+)", m.group(1)):
            out.update(str(k) for k in range(int(a), min(int(b), int(a) + 20) + 1))
    return out


def _paper_key(chunks: list) -> int:
    fields = ("row_label", "column_header", "value", "caption", "page", "row", "col")
    return hash(tuple((str(c.get("chunk_id")), str(c.get("block_type")), hash(str(c.get("text") or "")),
                       str(c.get("table_caption")), str(c.get("page_or_node")), c.get("char_start"), c.get("char_end"),
                       tuple(tuple(str(x.get(k)) for k in fields) for x in (c.get("table_cells") or [])
                             if isinstance(x, dict)))
                      for c in chunks if isinstance(c, dict)))


def _index(chunks: list, off: frozenset[str]) -> dict[str, Any]:
    chunks = chunks or []
    key = (_paper_key(chunks), off)
    idx = _CACHE.get(key)
    if idx is None:
        if len(_CACHE) > 64:
            _CACHE.clear()
        idx = _CACHE[key] = _build(chunks, off)
    return idx


def _build(chunks: list, off: frozenset[str]) -> dict[str, Any]:
    syn = "synonyms" not in off
    cells, seen = [], set()
    for ch_i, ch in enumerate(chunks):
        for x in (ch.get("table_cells") or []) if isinstance(ch, dict) else []:
            if not isinstance(x, dict):
                continue
            k = tuple(str(x.get(f, "")) for f in ("row_label", "column_header", "value", "caption"))
            if k not in seen:                                       # gate.paper_table_cells' de-duplication
                seen.add(k)
                parsed = _parse_cell(x, syn)
                completed_caption = _prep(ch.get("table_caption"))
                if parsed["cap"] and completed_caption.startswith(parsed["cap"]):
                    parsed["cap"] = completed_caption
                # A caption can end in one block and finish in the immediately
                # adjacent paragraph. Use only the contiguous same-page span,
                # stopping at its first short sentence; never unrelated prose.
                if re.search(r"\b(?:on|in|of|for|with)\s*$", parsed["cap"], re.I) and ch_i + 1 < len(chunks):
                    following = chunks[ch_i + 1]
                    if (isinstance(following, dict) and following.get("block_type") == "paragraph"
                            and ch.get("page_or_node") and following.get("page_or_node") == ch["page_or_node"]
                            and isinstance(ch.get("char_end"), int) and following.get("char_start") == ch["char_end"]):
                        continuation = re.match(r"^([a-z][^.;\d]{0,118}[.])(?:\s|$)", _prep(following.get("text")))
                        if continuation:
                            parsed["cap"] += " " + continuation.group(1)
                cells.append(parsed)
    texts = [_prep(ch.get("text")) for ch in chunks if isinstance(ch, dict) and ch.get("text")]
    sentences = [s for t in texts for s in _SENT_SPLIT.split(t) if s]
    tables: dict[tuple, dict] = {}
    for i, p in enumerate(cells):
        p["i"], p["tk"] = i, (p["cap"], str(p["raw"].get("page")))
        p["rform"], p["rbr"] = _form(_core(p["row"]), syn), _form(_bracket(p["row"]), syn)
        p["lforms"] = [_form(_core(x), syn) for x in p["levels"]]
        p["lbr"] = [_form(_bracket(x), syn) for x in p["levels"]]
        p["parts"] = [(lab, n, u, _form(_core(lab), syn)) for lab, n, u in p["parts"]]
        p["axes"] = {"r": p["rform"], **{("c", k): f for k, f in enumerate(p["lforms"])}}
        lab = _TABLE_LABEL.match(p["cap"])
        t = tables.setdefault(p["tk"], {"caption": p["cap"], "cells": [], "axes": {},
                                        "label": _tnum(lab.group(1)) if lab else None})
        t["cells"].append(i)
        for ax, f in p["axes"].items():
            if f:
                t["axes"].setdefault(ax, set()).add(f)
                t.setdefault("by_label", {}).setdefault((ax, f), []).append(i)
    for t in tables.values():
        ct = _tokens(t["caption"], syn)
        t["runs"] = {"".join(x[1] for x in ct[a:b]) for a in range(len(ct)) for b in range(a + 1, min(len(ct), a + 6) + 1)}
    q = {"dice"} if syn else set()
    for p in cells:
        q.add(p["lforms"][-1])
        q.update(part[3] for part in p["parts"])
    q = {x for x in q if len(x) >= 2}
    labels: dict[str, set] = {}
    for tk, t in tables.items():
        for ax, fs in t["axes"].items():
            for f in fs:
                if len(f) >= 2:
                    labels.setdefault(f, set()).add((tk, ax))
    forms = set(labels) | q
    declared: dict[str, str] = {}
    for s in sentences:
        for m in _DECLARE.finditer(s):
            declared.setdefault(_form(m.group(1), syn), s)
        for m in _NAMED_AS.finditer(s):
            if re.search(r"\b(?:we|our|us)\b", s[:m.start()], re.I):
                declared.setdefault(_form(m.group(1), syn), s)
    declared = {f: s for f, s in declared.items() if len(f) >= 2 and f not in _FUNCTION
                and f not in ("table", "figure", "fig", "section", "equation", "appendix")}
    group = {_canon(x, syn) for x in _GROUP_NOUNS}
    aliases: dict[str, dict[str, str]] = {}
    for s in sentences:
        ts = _tokens(s, syn)
        for k in range(1, len(ts)):
            if ts[k][1] not in group or s[ts[k - 1][3]:ts[k][2]] != " ":
                continue
            for a in range(max(0, k - 3), k):
                f = "".join(x[1] for x in ts[a:k])
                if f in labels and all(_SEP.fullmatch(s[ts[j][3]:ts[j + 1][2]]) for j in range(a, k - 1)):
                    aliases.setdefault(ts[k][1], {}).setdefault(f, s)
    for p in cells:
        own = []
        for ax, raw in [("r", p["row"])] + [(("c", k), x) for k, x in enumerate(p["levels"])]:
            core = _core(raw)
            if core and _own_label(raw):
                own.append((ax, "mark"))
            elif p["axes"][ax] and p["axes"][ax] in declared:
                own.append((ax, "declared"))
        p["own"] = own
    by_value: dict[str, list[int]] = {}
    for p in cells:
        for k in {p["central"], *(x[1] for x in p["parts"]), *(p["range"] or ())} - {None}:
            by_value.setdefault(k, []).append(p["i"])
    caption_scopes = [m.group(1) for t in tables.values()
                      for m in re.finditer(r"\b(?:on|in|across|under|among|within|using)\s+([^.;]{1,120})",
                                           t["caption"], re.I)]
    caption_terms = {tok[1] for scope in caption_scopes for tok in _tokens(scope, syn)
                     if tok[1] not in _FUNCTION | _GENERIC and not tok[1][0].isdigit()}
    return {"cells": cells, "tables": tables, "labels": labels, "q": q, "forms": forms,
            "caption_terms": caption_terms,
            "prefixes": {f[:k] for f in forms for k in range(1, len(f) + 1)}, "declared": declared,
            "aliases": aliases, "texts": texts, "raw_texts": [str(c.get("text") or "") for c in chunks if isinstance(c, dict)],
            "sentences": sentences, "syn": syn, "by_value": by_value}


# --- the ClaimFrame (PREREG D2, D6 local context) ----------------------------------------------------------------
_CLAUSE = re.compile(r";|\b(?:while|whereas|but)\b|(?<=[.!?])(?<!\bvs\.)(?<!\bal\.)(?<!\be\.g\.)(?<!\bi\.e\.)"
                     r"(?<!\bFig\.)(?<!\bEq\.)(?<!\bNo\.)\s+(?=[A-Z])")
_COMP = re.compile(r"\b(?:compared\s+(?:with|to)|in\s+comparison\s+(?:with|to)|relative\s+to|than|versus|vs\.?|"
                   r"against|unlike|over|outperform\w*|beat\w*|surpass\w*|exceed\w*|superior\s+to|inferior\s+to|"
                   r"similar\s+to|comparable\s+to|ahead\s+of|behind|(?:above|below)(?!\s*[\d.<>]))(?!\w)", re.I)
_COMP_STOP = re.compile(r"[,;:()\[\]]|\.(?=\s|$)")
_PAIR = re.compile(r"\b(?:vs\.?|versus|compared\s+(?:with|to)|against|than|outperform\w*|over|unlike|relative\s+to)"
                   r"(?!\w)", re.I)
_GOV = re.compile(r"^\s*(for|by|on|in|at|across|under|among|within|with|using)\s+", re.I)
_GOV_STOP = re.compile(r"[,;:()\[\]]|\.(?=\s|$)|\b(?:and|or|but|while|whereas|vs|versus|compared|than|respectively|"
                       r"which|that|to|from|where|when)\b", re.I)
_FRONTED = re.compile(r"^\s*(?:on|in|for|at|across|under|among|within|with|using|over)\s+[^,;]{1,80},", re.I)
_SETTING_TYPES = (
    ('confidence', re.compile(r'\bconfidence(?:\s+(?:thresholds?|values?|levels?|scores?))?\b', re.I)),
    ('learning_rate', re.compile(r'\blearning\s+rates?\b', re.I)),
    ('dropout', re.compile(r'\bdropout(?:\s+(?:rates?|probabilit(?:y|ies)))?\b', re.I)),
    ('batch_size', re.compile(r'\bbatch\s+sizes?\b', re.I)),
    ('epochs', re.compile(r'\bepochs?\b', re.I)),
    ('threshold', re.compile(r'\bthresholds?\b', re.I)),
    ('hyperparameter', re.compile(r'\bhyperparameters?\b', re.I)),
)


def _setting_type(text: str) -> tuple[str | None, int]:
    hits = [(m.end(), -i, kind) for i, (kind, rx) in enumerate(_SETTING_TYPES) for m in rx.finditer(text)]
    if not hits:
        return None, 0
    end, _, kind = max(hits)
    return kind, end


def _match_forms(w: str, toks: list, idx: dict) -> tuple[list[dict[str, Any]], list[tuple[int, int, str]]]:
    """D4: label and quantity forms equal to a contiguous run of claim tokens, maximal; compound names
    ("Swin UNETR", "UNet-based") are set aside as rejected."""
    forms, prefixes, n = idx["forms"], idx["prefixes"], len(toks)
    found = []
    for i in range(n):
        if toks[i][0] in ("vs", "Vs", "versus", "Versus"):
            continue
        acc = ""
        for j in range(i, min(n, i + 10)):
            if j > i and not _SEP.fullmatch(w[toks[j - 1][3]:toks[j][2]]):
                break
            acc += toks[j][1]
            if acc not in prefixes:
                break
            if acc in forms:
                found.append((i, j + 1, acc))
    keep = [x for x in found if not any(y != x and y[0] <= x[0] and x[1] <= y[1] for y in found)]
    covered = {k for a, b, _ in keep for k in range(a, b)}
    out, rejected = [], []
    for a, b, f in keep:
        s, e = toks[a][2], toks[b - 1][3]
        left = w[toks[a - 1][3]:s] if a > 0 else None
        right = w[e:toks[b][2]] if b < n else None
        if (left == "-" or right == "-"
                or (left == " " and a - 1 not in covered and toks[a - 1][0][:1].isupper()
                    and toks[a - 1][1] not in _FUNCTION
                    and not (toks[a - 1][1] == "row" and f.isdigit()))
                or (right == " " and b not in covered and toks[b][0][:1].isupper() and toks[b][1] not in _FUNCTION
                    and toks[b][1] not in idx["q"] and not _named(toks[b][0]))):
            rejected.append((s, e, f))
            continue
        br = re.match(r"\s*[\(\[]([^\)\]]{1,40})[\)\]]", w[e:])
        out.append({"s": s, "e": e, "form": f, "refs": idx["labels"].get(f, set()), "q": f in idx["q"],
                    "br": _form(br.group(1), idx["syn"]) if br and re.search(r"[A-Za-z]", br.group(1)) else None})
    return out, rejected


def _minus(spans: list[tuple[int, int]], cut: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    for s, e in spans:
        pieces = [(s, e)]
        for a, b in cut:
            pieces = [x for ps, pe in pieces for x in ((ps, min(pe, a)), (max(ps, b), pe)) if x[0] < x[1]]
        out += pieces
    return out


def _in(s: int, e: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= s and e <= b for a, b in spans)


def _frame(w: str, idx: dict[str, Any], off: frozenset[str]) -> dict[str, Any]:
    toks = _tokens(w, idx["syn"])
    ms = mentions(w)
    matches, rejected = _match_forms(w, toks, idx)
    covered = [(x["s"], x["e"]) for x in matches]
    own = [(m.start(), m.end()) for m in _OWN_REF.finditer(w)]
    alias = [(t[2], t[3], t[1]) for t in toks if t[1] in idx["aliases"]]
    named = [(t[2], t[3], t[1]) for t in toks if _named(t[0]) and t[1] not in idx["q"] and t[1].lower() not in _STAT
             and not _in(t[2], t[3], covered) and not _UNIT_AFTER.fullmatch(" " + t[0])
             and not re.search(r"(?i:tables?|tab\.|fig\.?|figures?)\s*$", w[max(0, t[2] - 8):t[2]])]
    bounds = [0] + [x for m in _CLAUSE.finditer(w) for x in m.span()] + [len(w)]
    clauses = [(bounds[k], bounds[k + 1]) for k in range(0, len(bounds), 2)]
    starts = [m["start"] for m in ms]
    comps = []
    for c in _COMP.finditer(w):
        stop = _COMP_STOP.search(w, c.end())
        end = min([stop.start() if stop else len(w)] + [s for s in starts if s >= c.end()]
                  + [b for a, b in clauses if a <= c.start() < b])
        comps.append((c.start(), end))
    fr = {"w": w, "toks": toks, "mentions": ms, "matches": matches, "rejected": rejected, "own": own, "alias": alias,
          "named": named, "comps": comps, "tables": _tables_named(w) if "table_mention" not in off else set()}
    for ci, (cs, ce) in enumerate(clauses):
        cm = [m for m in ms if cs <= m["start"] < ce]
        if not cm:
            continue
        ccomps = [c for c in comps if cs <= c[0] < ce]
        prefix = _minus([(cs, cm[0]["start"])], ccomps)
        fm = _FRONTED.match(w[cs:ce])
        fronted = [(cs, cs + fm.end() - 1)] if fm and cs + fm.end() <= cm[0]["start"] else []
        att = cs
        for k, m in enumerate(cm):
            gov = _GOV.match(w[m["end"]:ce])
            gspan, gkind = None, None
            if gov:
                stop = _GOV_STOP.search(w, m["end"] + gov.end())
                ge = min([stop.start() if stop and stop.start() < ce else ce] + [x["start"] for x in cm[k + 1:]]
                         + [m["end"] + gov.end() + 80])
                gspan, gkind = (m["end"] + gov.start(1), ge), gov.group(1).lower()
            q = w.rfind("(", att, m["start"])
            head = []
            if q >= 0 and w.rfind(")", q, m["start"]) < 0 and not re.search(
                    r"[A-Za-z]", re.sub(r"\b(?:vs\.?|versus)", "", w[q + 1:m["start"]], flags=re.I)):
                head = [(s, e) for s, e in covered + own + [(a, b) for a, b, _ in alias]
                        if q - 3 <= e <= q and not w[e:q].strip()]
            m.update(clause=ci, local=[(att, m["start"])], head=head, gov=gspan, gov_kind=gkind,
                     attach=max(m["end"], gspan[1] if gspan else m["end"]), prefix=prefix, fronted=fronted,
                     comps=ccomps, role="single")
            att = m["attach"]
        for k in range(len(cm) - 1):                                  # roles (PREREG D9 comparisons)
            m, nx = cm[k], cm[k + 1]
            if re.search(r"\bfrom\s*$", w[m["local"][0][0]:m["start"]], re.I) and \
                    re.search(r"\bto\s*$", w[m["attach"]:nx["start"]], re.I):
                m["role"], nx["role"] = "from", "to"
            elif _PAIR.search(w[m["end"]:nx["start"]]):
                if m["role"] == "single":
                    m["role"] = "primary"
                nx["role"] = "comparator"
        for m in cm:
            subj_gov = [m["gov"]] if m["gov"] and m["gov_kind"] in ("for", "by") else []
            if m["role"] == "from":
                m["L_local"] = m["head"] + subj_gov
            else:
                m["L_local"] = _minus(m["local"], ccomps) + m["head"] + subj_gov
            if m["role"] == "comparator":
                m["L_fb"] = list(ccomps)
            elif m["role"] == "from":
                m["L_fb"] = []
            else:
                m["L_fb"] = list(prefix)
                pb = _PASSIVE_BY.search(w, m["attach"], ce) if len(cm) == 1 else None
                if pb:
                    stop = _GOV_STOP.search(w, pb.end())
                    m["L_fb"].append((pb.end(), stop.start() if stop and stop.start() < ce else ce))
            qual_gov = [m["gov"]] if m["gov"] else []
            m["ctx"] = list(prefix) + fronted + _minus(m["local"], ccomps) + m["head"] + qual_gov
            m["qphr"] = fronted + qual_gov
            noun = [(m["end"], m["count_end"])] if m.get("count_end") else []
            m["levels"] = [m["local"] + m["head"] + qual_gov + noun, [(cs, cm[0]["start"])], [(cs, ce)]]
            prev = next((v['end'] for v in reversed(cm) if v['start'] < m['start']), cs)
            kind, end = _setting_type(w[prev:m['start']])
            # An explicit nearer measured quantity supersedes an earlier setting.
            if kind and any(x['q'] and prev + end < x['e'] <= m['start'] for x in matches):
                kind = None
            m['quantity_type'] = kind
            _views(m, fr, idx, off)
    return fr


def _views(m: dict, fr: dict, idx: dict, off: frozenset[str]) -> None:
    """Everything about m's regions that does not depend on the cell, computed once per value."""
    loc, w = m["L_local"], fr["w"]
    cues = (any(_in(x["s"], x["e"], loc) and x["refs"] and not x["q"] for x in fr["matches"])
            or any(_in(s, e, loc) for s, e, _ in fr["named"]) or any(_in(s, e, loc) for s, e in fr["own"])
            or any(_in(s, e, loc) for s, e, _ in fr["alias"]))
    region = loc if cues else loc + m["L_fb"]
    m["region"] = region
    m["r_matches"] = [dict(x, local=_in(x["s"], x["e"], loc), text=w[x["s"]:x["e"]]) for x in fr["matches"]
                      if _in(x["s"], x["e"], region)]
    m["r_own"] = [(s, e, _in(s, e, loc)) for s, e in fr["own"] if _in(s, e, region)]
    m["own_text"] = w[m["r_own"][0][0]:m["r_own"][0][1]] if m["r_own"] else ""
    m["r_alias"] = [(s, e, f, _in(s, e, loc)) for s, e, f in fr["alias"] if _in(s, e, region)]
    m["alias_text"] = {s: w[s:e] for s, e, _, _ in m["r_alias"]}
    m["r_rejected"] = {f for s, e, f in fr["rejected"] if _in(s, e, region)}
    m["r_names"] = ([x["form"] for x in m["r_matches"] if x["refs"] and not x["q"]]
                    + [f for s, e, f in fr["named"] if _in(s, e, region)])
    m["c_matches"] = [x for x in fr["matches"] if x["refs"] and not x["q"] and _in(x["s"], x["e"], m["ctx"])]
    m["q_forms"] = ([x["form"] for x in fr["matches"] if x["refs"] and not x["q"] and _in(x["s"], x["e"], m["qphr"])]
                    + [f for s, e, f in fr["named"] if _in(s, e, m["qphr"])])
    m["q_forms"] += [t[1] for t in fr["toks"] if _in(t[2], t[3], m["qphr"])
                     and t[1] in idx["caption_terms"] and t[1] not in idx["q"]]
    m["lv_terms"] = []
    for level, spans in enumerate(m["levels"]):                  # level terms: form -> (claim text, quantity-like)
        terms = {x["form"]: (w[x["s"]:x["e"]], x["q"]) for x in fr["matches"] if _in(x["s"], x["e"], spans)
                 and not (level == 2 and x['q'] and any(
                     m['end'] <= x['s'] < x['e'] <= other['start']
                     for other in fr['mentions'] if other['start'] > m['start']))}
        if level == 0 and m["count"] and "count_attribute" not in off:
            terms["#" + _canon(m["count"], idx["syn"])] = (m["count"], True)
        m["lv_terms"].append(terms)


# --- links of one value to one cell (PREREG D6) -----------------------------------------------------------------
def _carried(p: dict, part: int | None, idx: dict) -> set[str]:
    t = idx["tables"][p["tk"]]
    out = {f for f in p["axes"].values() if f} | t["runs"]
    if part is not None:
        out.add(p["parts"][part][3])
    return out


def _qnames(p: dict, part: int | None, idx: dict, off: frozenset[str]) -> dict[str, str]:
    """Quantity names of the cell for this value: form -> channel (PREREG D6 quantity)."""
    if part is not None:
        return {p["parts"][part][3]: "part"} if "caption_quantity" not in off else {}
    out = {p["lforms"][-1]: "header"} if p["lforms"][-1] else {}
    if "caption_quantity" not in off:
        if p["rform"]:
            out.setdefault(p["rform"], "row")
        for f in sorted(idx["tables"][p["tk"]]["runs"] & idx["q"]):
            out.setdefault(f, "caption")
    if p["count"] is not None and "count_attribute" not in off:
        out.setdefault("#" + (p["count"] or "*"), "count")
    return out


def _subject_cands(m: dict, p: dict, idx: dict, off: frozenset[str]) -> list[dict]:
    """Subject evidence for p in m's subject region (PREREG D6 subject): local evidence first, labels before aliases."""
    out = []
    for x in m["r_matches"]:
        for ax, f in p["axes"].items():
            if f != x["form"] or (ax != "r" and "column_subject" in off):
                continue
            br = p["rbr"] if ax == "r" else p["lbr"][ax[1]]
            if x["br"] and br and x["br"] != br:
                continue
            out.append({"kind": "label", "term": f, "axis": ax, "local": x["local"], "text": x["text"], "weak": x["q"]})
    if "own_alias" not in off and p["own"] and m["r_own"]:
        s, e, loc = m["r_own"][0]
        ax, how = p["own"][0]
        out.append({"kind": "own_alias", "term": p["axes"][ax], "axis": ax, "local": loc, "text": m["own_text"],
                    "ambiguous": how == "declared" and len(idx["declared"]) > 1,
                    "span": idx["declared"].get(p["axes"][ax]) if how == "declared" else None})
    for s, e, noun, loc in m["r_alias"]:
        targets = idx["aliases"][noun]
        for ax, f in p["axes"].items():
            if f in targets and (ax == "r" or "column_subject" not in off):
                out.append({"kind": "group_alias", "term": f, "axis": ax, "local": loc, "text": m["alias_text"][s],
                            "span": targets[f], "ambiguous": len(targets) > 1})
    # A metric label mentioned beside a value is weak subject evidence. Prefer
    # an explicit entity/own-method link before reinterpreting that metric as
    # the subject and a generic caption term as the quantity.
    out.sort(key=lambda x: (bool(x.get("weak")), not x["local"], x["kind"] != "label"))
    strong = [x for x in out if not x.get('weak')]
    return strong or out


def links(m: dict, p: dict, fr: dict, idx: dict, off: frozenset[str], part: int | None = None) -> dict[str, Any]:
    """Subject, quantity, conflicts, qualifier matches and table mention of value m in cell p."""
    t = idx["tables"][p["tk"]]
    subs = _subject_cands(m, p, idx, off)
    carried, qn = _carried(p, part, idx), _qnames(p, part, idx, off)
    tried = []
    for sub in subs + [None]:
        conf, co = [], False
        ax_s = sub["axis"] if sub else None
        subj_forms = set(t["axes"].get(ax_s, set())) if sub else set()
        for x in m["r_matches"]:                                    # C1 on the subject axis
            for tk, ax in x["refs"]:
                if tk != p["tk"]:
                    continue
                pf = p["axes"].get(ax)
                if pf == x["form"]:
                    br = p["rbr"] if ax == "r" else p["lbr"][ax[1]]
                    if x["br"] and br and x["br"] != br:
                        conf.append("subject_label")                # "UNet (scratch)" named, cell "UNet (pretrained)"
                elif ax == ax_s or (sub is None and not x["q"]):
                    if sub and "subject_label" not in conf and _co_named(m, p, ax, x["form"], idx):
                        co = True
                    else:
                        conf.append("subject_label")
        if sub:                                                     # C1 on the qualifier axes
            for x in m["c_matches"]:
                if any(tk == p["tk"] and ax != ax_s and p["axes"].get(ax) != x["form"] for tk, ax in x["refs"]):
                    conf.append("qualifier_label")
        if m["r_rejected"] & set(p["axes"].values()):
            conf.append("compound_name")                             # "Swin UNETR" named, cell "UNETR"
        if m["r_own"] and not p["own"]:
            conf.append("own_reference")                             # C2
        if any(f not in carried for f in m["q_forms"]):
            conf.append("qualifier_unexplained")                     # C4
        if (not sub or sub["kind"] != "label") and any(f not in carried for f in m["r_names"]):
            conf.append("name_unexplained")                          # C5: no label subject beside an unexplained name
        sterm = sub["term"] if sub else None
        terms: dict[str, tuple[str, bool]] = {}
        fallback: dict[str, tuple[str, bool]] = {}
        for lv in m["lv_terms"]:                                    # the nearest level naming a quantity term
            terms = {f: x for f, x in lv.items() if f != sterm and f not in subj_forms}
            if any(isq for _, isq in terms.values()):
                break
            fallback = fallback or terms
            terms = {}
        terms = terms or fallback                                   # else the nearest other label (a row quantity)
        qlink = None
        for f, (txt, _) in sorted(terms.items(), key=lambda item: -_QRANK.get(qn.get(item[0], "count"), 0)):
            if f in qn or (f.startswith("#") and "#*" in qn):
                qlink = {"kind": qn.get(f, "count"), "term": f, "text": txt}
                break
        if qlink and qlink["kind"] == "caption":
            # A caption lists what a table contains. It cannot override an
            # explicit competing quantity on the cell's row/column axis.
            qf = qlink["term"]
            for ax, forms in t["axes"].items():
                if ax == ax_s:
                    continue
                pf = p["axes"].get(ax)
                if (qf in forms and pf != qf) or (pf != qf and pf in idx["q"]
                                                and pf in t["runs"] and pf not in _GENERIC):
                    conf.append("quantity_axis")
        if any(f.startswith("#") and p["count"] not in (None, "", f[1:]) or isq and not f.startswith("#")
               and f not in carried for f, (_, isq) in terms.items()):
            conf.append("quantity_term")
        if m.get('quantity_type'):
            quantity_source = {'header': p['levels'][-1], 'row': p['row'], 'caption': p['cap'],
                               'part': p['parts'][part][0] if part is not None else ''}
            source = quantity_source.get(qlink['kind'], '') if qlink else ''
            if _setting_type(source)[0] != m['quantity_type']:
                conf.append('quantity_type')
        if not _unit_ok(m, p, part):
            conf.append("unit")
        if fr["tables"] and t["label"] not in fr["tables"]:
            conf.append("table_mention")
        tried.append({"subject": sub, "quantity": qlink, "conflicts": sorted(set(conf)), "co_named": co})
        if sub and qlink and not conf:
            break
    strong = [x for x in tried if x["subject"] and (x["quantity"] or not x["subject"].get("weak"))]
    best = next((x for x in strong if x["quantity"] and not x["conflicts"]), None) \
        or next((x for x in strong if x["quantity"]), None) or (strong[0] if strong else tried[-1])
    sterm = (best["subject"] or {}).get("term")
    return {**best, "part": part, "has_subject": bool(strong), "has_quantity": bool(best["quantity"]),
            "eligible": bool(best["subject"] and best["quantity"] and not best["conflicts"]),
            "qual": frozenset(x["form"] for x in m["c_matches"] if x["form"] != sterm and x["form"] in carried),
            "tm": int(bool(fr["tables"]) and t["label"] in fr["tables"])}


def _co_named(m: dict, p: dict, ax: Any, form: str, idx: dict) -> bool:
    """The claim also names `form`, another subject of p's table holding the same value in an otherwise equal cell."""
    for i in idx["tables"][p["tk"]].get("by_label", {}).get((ax, form), []):
        o = idx["cells"][i]
        if o["axes"].get(ax) == form and all(o["axes"].get(a) == f for a, f in p["axes"].items() if a != ax) \
                and _value_hits(m, o):
            return True
    return False


# --- the choice among eligible cells (PREREG D8) ----------------------------------------------------------------
_QRANK = {"header": 3, "row": 2, "part": 2, "caption": 1, "count": 0}


def _vector(lk: dict) -> tuple:
    s = lk["subject"]
    return (2 * bool(s["local"]) + (s["kind"] == "label"), _QRANK[lk["quantity"]["kind"]], lk["qual"], lk["tm"])


def _dominates(a: tuple, b: tuple) -> bool:
    return (a[0] >= b[0] and a[1] >= b[1] and a[2] >= b[2] and a[3] >= b[3]
            and (a[0] > b[0] or a[1] > b[1] or a[2] > b[2] or a[3] > b[3]))


def _choose(el: list[tuple[dict, dict]]) -> tuple[list[tuple[dict, dict]], str | None]:
    """The undominated eligible cells and, when more than one remains or the subject is ambiguous, the code."""
    vecs = [_vector(lk) for _, lk in el]
    win = [x for k, x in enumerate(el) if not any(_dominates(vecs[j], vecs[k]) for j in range(len(el)) if j != k)]
    if len(win) == 1 and not win[0][1]["co_named"] and not win[0][1]["subject"].get("ambiguous"):
        return win, None
    if len({lk["subject"]["term"] for _, lk in win}) > 1 or any(lk["co_named"] or lk["subject"].get("ambiguous")
                                                               for _, lk in win):
        return win, "ambiguous_subject"
    if len({lk["quantity"]["term"] for _, lk in win}) > 1:
        return win, "ambiguous_quantity"
    if len({p["tk"] for p, _ in win}) > 1:
        return win, "duplicate_quantity_context"
    if len({tuple(sorted((str(a), f) for a, f in p["axes"].items())) for p, _ in win}) > 1:
        return win, "insufficient_qualifier"
    return win, "duplicate_value"


# --- the verifier (PREREG D10): re-reads the raw cell and the claim with its own string tests ------------------------
def _span_in(span: str, chunks: list) -> bool:
    return bool(span) and any(span in str(c.get("text") or "") for c in chunks if isinstance(c, dict))


def verify(claim: str, m: dict, p: dict, chunks: list, off: frozenset[str], span: str | None = None,
           lk: dict | None = None) -> str | None:
    """None when the binding holds; otherwise the first failing check."""
    raw = p.get("raw")
    if not any(raw is x or raw == x for c in chunks if isinstance(c, dict) for x in (c.get("table_cells") or [])):
        return "not_an_attached_cell"
    # Re-read the claim and attached cell; candidate scores/links are not proof.
    fresh_idx = _index(chunks, off)
    fresh_fr = _frame(_prep(claim), fresh_idx, off)
    fresh_m = next((v for v in fresh_fr["mentions"] if v["start"] == m["start"] and v["tok"] == m["tok"]), None)
    fresh_p = next((c for c in fresh_idx["cells"] if c["raw"] == raw), None)
    if not fresh_m or fresh_p is None or fresh_m.get("negated") or fresh_m["threshold"] or fresh_m["delta"]:
        return "claim_structure"
    parts = _value_hits(fresh_m, fresh_p)
    if not parts:
        return "value_structure"
    fresh_links = [links(fresh_m, fresh_p, fresh_fr, fresh_idx, off, part) for part in parts]
    alias = bool(lk and lk.get("subject", {}).get("kind") == "llm_alias")
    verified_link = next((link for link in fresh_links if link["eligible"]), None)
    if verified_link is None and alias:
        clean = next((link for link in fresh_links if link["has_quantity"] and not link["conflicts"]), None)
        if clean is not None:
            verified_link = dict(clean, subject=lk["subject"])
    if verified_link is None:
        return "subject_quantity_or_qualifier"
    m, p, lk = fresh_m, fresh_p, verified_link
    value = _prep(raw.get("value"))
    text = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", norm(value))
    found = set(re.findall(r"(?<![\d.])-?\d*\.?\d+", text))
    tok = m["tok"]
    if tok not in found and not (tok.startswith("0.") and tok[1:] in found):
        return "value_not_in_cell"
    if m["range"] and not all(x.lstrip("-") in text for x in m["range"]):
        return "value_not_in_cell"
    cf, sub, q = _flat(claim), lk["subject"], lk["quantity"]
    labels = [_core(raw.get("row_label"))] + [_core(x) for x in _prep(raw.get("column_header")).split(" / ")]
    lflat = [_flat(x) for x in labels if _flat(x)]
    if sub["kind"] == "label":
        if _flat(sub["text"]) not in cf or _flat(sub["text"]) not in lflat:
            return "subject"
    elif sub["kind"] == "own_alias":
        raw_labels = [_prep(raw.get('row_label'))] + _prep(raw.get('column_header')).split(' / ')
        if not _OWN_REF.search(_prep(claim)) or not (any(_own_label(x) for x in raw_labels)
                                                       or (sub.get("span") and _span_in(sub["span"], chunks))):
            return "subject"
    else:                                                           # group or judge alias: a verbatim paper span
        ev = span if sub["kind"] == "llm_alias" else sub.get("span")
        if not ev or not _span_in(ev, chunks) or not any(x in _flat(ev) for x in lflat):
            return "subject"
        if sub["kind"] == "group_alias" and _flat(sub["text"]) not in _flat(ev):
            return "subject"
        if sub["kind"] == "llm_alias" and not any(x in _flat(ev) for x in sub.get("words", [])):
            return "subject"
    if q["kind"] == "count":
        noun, heads = _flat(m["count"] or ""), [_flat(labels[-1]), _flat(labels[0])]
        if not noun or not any(noun in h or h in ("n", "count", "no") for h in heads):
            return "quantity"
    else:
        src = {"header": labels[-1], "row": labels[0], "caption": raw.get("caption"),
               "part": p["parts"][lk["part"]][0] if lk.get("part") is not None else ""}[q["kind"]]
        if not _flat(q["text"]) or _flat(q["text"]) not in cf or _flat(q["text"]) not in _flat(src):
            return "quantity"
    if m["unit"]:
        units = {_unit(u) for u in _UNIT_IN_VALUE.findall(value)} | {
            _unit(u) for x in (_prep(raw.get("row_label")), _prep(raw.get("column_header")))
            for u in _UNIT_IN_LABEL.findall(x.translate(_SUPER))}
        if m["unit"] == "%":
            if "%" not in value + str(raw.get("column_header")) + str(raw.get("row_label")) + str(raw.get("caption")):
                return "unit"
        elif units and m["unit"] not in units:
            return "unit"
    named = _tables_named(_prep(claim)) if "table_mention" not in off else set()
    lab = _TABLE_LABEL.match(_prep(raw.get("caption")))
    if named and (not lab or _tnum(lab.group(1)) not in named):
        return "table_mention"
    return None


# --- the LLM judge (PREREG E) -----------------------------------------------------------------------------------
_LLM_VERSION = "phase10-judge-1"
_LLM_SYSTEM = ("You link one number in a scientific claim to one table cell. You get the claim, the number, candidate "
               "cells (id, row, column, value, caption) and sentences from the paper. Choose the candidate whose subject "
               "and quantity the claim states for that number, or \"none\" if the claim does not single one out. Reply "
               "with JSON only: {\"choice\": \"<candidate id or none>\", \"span\": \"<text copied exactly from the paper "
               "sentences or captions that names the chosen cell's subject>\"}.")
_LLM_MEM: dict[str, dict[str, dict]] = {}
_PRIMED: list[bool] = []


def _llm_cfg() -> dict:
    import yaml
    root = Path(__file__).resolve().parents[2]
    return yaml.safe_load((root / "configs" / "staging_config.yaml").read_text(encoding="utf-8"))["llm"]


def _llm_cache(path: Path) -> dict[str, dict]:
    if str(path) not in _LLM_MEM:
        recs: dict[str, dict] = {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("run") == "fresh" and isinstance(r.get("key"), str):
                recs.setdefault(r["key"], r)
        _LLM_MEM[str(path)] = recs
    return _LLM_MEM[str(path)]


def _llm_call(request: dict) -> dict | None:
    """One judge request. RGPT_BINDER_LLM_MODE: fresh (call Ollama, append to the cache), replay (cache only),
    fresh2 (call again, appended as a second run). A cache line is keyed by the SHA-256 of the request."""
    mode = os.environ.get("RGPT_BINDER_LLM_MODE", "fresh").strip().lower()
    path = Path(os.environ.get("RGPT_BINDER_LLM_CACHE")
                or Path(__file__).resolve().parents[1] / "evaluation" / "binder_10" / "llm_cache.jsonl")
    cfg = _llm_cfg()
    key = hashlib.sha256(json.dumps({"version": _LLM_VERSION, "model": cfg["model"], "system": _LLM_SYSTEM,
                                     "request": request}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    cache = _llm_cache(path)
    if mode == "replay":
        rec = cache.get(key)
        return rec["response"] if rec else {"_unavailable": "cache_miss"}
    from ..summarization.summarize import call_ollama_json, prime_ollama_cache
    err = None
    try:
        if not _PRIMED:
            prime_ollama_cache(cfg)
            _PRIMED.append(True)
        resp = call_ollama_json(cfg["base_url"], cfg["model"], _LLM_SYSTEM, json.dumps(request, ensure_ascii=False),
                                temperature=float(cfg.get("temperature", 0)), seed=cfg.get("seed", 42),
                                timeout=int(cfg.get("timeout_seconds", 300)), num_predict=256)
    except Exception as e:                                          # Ollama down: recorded; the value stays unbound
        resp, err = None, f"{type(e).__name__}: {e}"
    line = {"key": key, "run": "fresh" if mode == "fresh" else mode, "request": request, "response": resp, "error": err}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    if mode == "fresh":
        cache.setdefault(key, line)
    return resp if isinstance(resp, dict) else {"_unavailable": "llm_error"}


def _subject_words(m: dict, fr: dict) -> list[str]:
    """Words naming the claim's subject: its subject region before the verb, without function, generic or digit words."""
    out = []
    for s, e in m["region"]:
        seg = fr["w"][s:e]
        v = _VERB.search(seg)
        seg = seg[:v.start()] if v else seg
        out += [t[1] for t in _tokens(seg, True) if len(t[1]) >= 3 and t[1] not in _FUNCTION and t[1] not in _GENERIC
                and not t[1][0].isdigit()]
    return sorted(set(out))


def _judge(fr: dict, m: dict, pool: list[tuple[dict, dict]], idx: dict, kind: str, words: list[str]):
    w = fr["w"]
    cands = [{"id": f"k{i + 1}", "row": p["row"], "column": p["col"], "value": p["value"], "caption": p["cap"][:240]}
             for i, (p, _) in enumerate(pool)]
    keys = {_flat(x) for p, _ in pool for x in [_core(p["row"])] + [_core(y) for y in p["levels"]]} | set(words)
    keys = {k for k in keys if len(k) >= 3}
    evidence = [s[:300] for s in idx["sentences"] if any(k in _flat(s) for k in keys)][:8]
    request = {"task": kind, "claim": w, "number": m["tok"], "candidates": cands, "paper_sentences": evidence}
    resp = _llm_call(request)
    info: dict[str, Any] = {"kind": kind, "candidates": [c["id"] for c in cands]}
    if not isinstance(resp, dict) or resp.get("_unavailable"):
        info["result"] = resp.get("_unavailable") if isinstance(resp, dict) else "llm_error"
        return None, None, info
    choice = str(resp.get("choice") if resp.get("choice") is not None else "none").strip()
    span = resp.get("span") if isinstance(resp.get("span"), str) else ""
    info.update(choice=choice, span=span)
    if choice.lower() in ("none", ""):
        info["result"] = "none"
        return None, None, info
    ids = [c["id"] for c in cands]
    if choice not in ids:
        raise LLMViolation(f"judge choice {choice!r} is not one of {ids} (claim {w[:120]!r})")
    sp = span
    if not sp:
        info["result"] = "rejected_empty_span"
        return None, None, info
    supplied = evidence + [c["caption"] for c in cands]
    if not any(sp in t for t in supplied) or not any(sp in t for t in idx["raw_texts"]):
        raise LLMViolation(f"judge span {span[:160]!r} is not in its input (claim {w[:120]!r})")
    info["result"] = "accepted"
    return pool[ids.index(choice)], sp, info


# --- the binder ----------------------------------------------------------------------------------------------------
def _cell_key(p: dict) -> dict:
    r = p["raw"]
    return {"row": r.get("row_label"), "col": r.get("column_header"), "value": r.get("value"), "caption": r.get("caption")}


def _table_type(p: dict, idx: dict) -> str:
    sib = [c for c in idx["cells"] if c["cap"] == p["cap"]]          # gate._table_type_for groups by caption
    return classify_table_v2(str(p["raw"].get("caption") or ""), {str(c["raw"].get("column_header") or "") for c in sib},
                             {str(c["raw"].get("row_label") or "") for c in sib})


def _bind_v2(value: str, chunks: list[dict[str, Any]], llm: bool = False) -> dict[str, Any]:
    """The phase 10 binder (PREREG D): gate.structural_bind's contract, plus binding_type, bindings, abstain_code
    (ambiguity, partial binding, failed verification) and v2_trace."""
    off = _off()
    idx = _index(chunks, off)
    if not idx["cells"]:
        return {"structured": False, "status": "pdf_only"}
    w = _prep(value)
    fr = _frame(w, idx, off)
    if not fr["mentions"]:
        return {"structured": True, "status": "no_number"}
    trace, bindings, codes, failures, any_cand, required = [], [], [], [], False, 0
    for m in fr["mentions"]:
        tr: dict[str, Any] = {"tok": m["tok"], "role": m.get("role"), "candidates": [], "eligible": []}
        trace.append(tr)
        if m["threshold"] or m["delta"] or m.get("negated") or "L_local" not in m:
            tr["outcome"] = "threshold" if m["threshold"] else ("delta" if m["delta"] else "non_equality")
            continue
        cands: list[tuple[dict, dict, int | None]] = []
        for i in dict.fromkeys(idx["by_value"].get(m["tok"], [])):
            p = idx["cells"][i]
            for part in _value_hits(m, p):
                cands.append((p, links(m, p, fr, idx, off, part), part))
        tr["n_candidates"] = len(cands)
        tr["candidates"] = [_cell_key(p) for p, _, _ in cands[:TRACE_CAP]] if len(trace) <= 16 else []
        any_cand = any_cand or bool(cands)
        linked = [(p, lk) for p, lk, _ in cands if lk["has_subject"] or lk["has_quantity"]]
        if not linked or ("multi_binding" in off and required):
            tr["outcome"] = "not_required"
            continue
        required += 1
        el = [(p, lk) for p, lk, _ in cands if lk["eligible"]]
        tr["eligible"] = [_cell_key(p) for p, _ in el]
        if el:
            win, code = _choose(el)
            if code and llm and 2 <= len(win) <= 5:
                pick, span, info = _judge(fr, m, win, idx, "ambiguity", _subject_words(m, fr))
                tr["llm"] = info
                if pick:
                    win, code = [(pick[0], dict(pick[1], llm_span=span))], None
            if code:
                tr["outcome"] = code
                codes.append(code)
                continue
            bindings.append((m, win[0][0], win[0][1]))
            tr["outcome"] = "bound"
            continue
        wrong = [(p, lk) for p, lk in linked if lk["conflicts"]]
        pool = [(p, lk) for p, lk in linked if not lk["has_subject"] and lk["has_quantity"] and not lk["conflicts"]]
        words = _subject_words(m, fr)
        if llm and not wrong and pool and len(pool) <= 5 and words:
            pick, span, info = _judge(fr, m, pool, idx, "alias", words)
            tr["llm"] = info
            if pick:
                p, lk = pick
                lk = dict(lk, subject={"kind": "llm_alias", "term": None, "axis": None, "local": False,
                                       "text": span, "words": words}, llm_span=span, eligible=True)
                if verify(w, m, p, chunks, off, span, lk) is None:
                    bindings.append((m, p, lk))
                    tr["outcome"] = "bound"
                    continue
                info["result"] = "rejected_by_verifier"
        tr["outcome"] = "wrong" if wrong else "unresolved"
        tr["conflicts"] = sorted({c for _, lk in wrong for c in lk["conflicts"]})
        failures.append(wrong[0] if wrong else None)
    out: dict[str, Any] = {"structured": True, "binder": "v2_llm" if llm else "v2", "v2_trace": {"mentions": trace}}
    if codes:
        out.update(status=codes[0], abstain_code=codes[0], reason=f"a value is {codes[0]}")
        return out
    if not required:
        out.update(status="not_bindable" if any_cand else "not_a_table_claim",
                   reason="no cell holding a claim value has a subject or quantity link to it" if any_cand
                   else "no claim value is in an attached cell")
        return out
    if not bindings:
        bad = next((x for x in failures if x), None)
        if bad:
            out.update(status="wrong_cell", reason="every cell holding the value conflicts with the claim: "
                       + ", ".join(bad[1]["conflicts"]),
                       candidate={"row": bad[0]["raw"].get("row_label"), "col": bad[0]["raw"].get("column_header")})
        else:
            out.update(status="not_bindable", reason="a required value has no subject or no quantity link")
        return out
    for m, p, lk in bindings:
        why = verify(w, m, p, chunks, off, lk.get("llm_span"), lk)
        if why:
            out.update(status="deterministic_verification_failed", abstain_code="deterministic_verification_failed",
                       reason=f"verifier: {why} ({m['tok']})")
            return out
    recs = [{"number": m["tok"], "cell": _cell_key(p), "role": m.get("role"), "subject": lk["subject"]["kind"],
             "subject_text": lk["subject"]["text"], "quantity": lk["quantity"]["kind"],
             "quantity_text": lk["quantity"]["text"], **({"llm_span": lk["llm_span"]} if lk.get("llm_span") else {}),
             **({"alias_span": lk["subject"]["span"]} if lk["subject"].get("span") else {})}
            for m, p, lk in bindings]
    if failures:
        out.update(status="partial_binding", abstain_code="partial_binding", binding_type=PARTIAL, bindings=recs,
                   reason=f"{len(bindings)} of {required} required values bound")
        return out
    subjects = {lk["subject"]["term"] or lk["subject"]["text"] for _, _, lk in bindings}
    types = [_table_type(p, idx) for _, p, _ in bindings]
    out.update(status="bound", number=recs[0]["number"], cell=recs[0]["cell"],
               table_type=next((x for x in types if x != "results"), "results"), bindings=recs,
               binding_type=SINGLE if len(recs) == 1 else (MULTI if len(subjects) == 1 else COMPARISON))
    return out


def structural_bind_v2(value: str, chunks: list[dict[str, Any]], llm: bool = False) -> dict[str, Any]:
    out = _bind_v2(value, chunks, llm)
    if llm or out['status'] not in ('not_bindable', 'not_a_table_claim'):
        return out
    if any(m.get('conflicts') for m in out.get('v2_trace', {}).get('mentions', [])):
        return out
    legacy = G._structural_bind_legacy(value, chunks)
    if legacy['status'] != 'bound':
        return out
    off, w = _off(), _prep(value)
    idx = _index(chunks, off)
    fr = _frame(w, idx, off)
    required = []
    for m in fr['mentions']:
        if m['threshold'] or m['delta'] or m.get('negated') or 'L_local' not in m:
            continue
        linked = []
        for i in dict.fromkeys(idx['by_value'].get(m['tok'], [])):
            p = idx['cells'][i]
            for part in _value_hits(m, p):
                lk = links(m, p, fr, idx, off, part)
                if lk['has_subject'] or lk['has_quantity']:
                    linked.append((p, lk))
        if linked:
            required.append((m, linked))
    # Legacy provides one cell. It cannot cover multiple required values or
    # resolve ambiguity by its original ordering. Text-only values stay outside
    # this required set, exactly as in the main binder.
    if len(required) != 1:
        return out
    m, linked = required[0]
    eligible = [(p, lk) for p, lk in linked if lk['eligible']]
    if not eligible:
        return out
    winners, code = _choose(eligible)
    if code or len(winners) != 1:
        return out
    p, lk = winners[0]
    if _cell_key(p) != legacy['cell'] or verify(w, m, p, chunks, off, lk=lk) is not None:
        return out
    record = {'number': m['tok'], 'cell': _cell_key(p), 'role': m.get('role'),
              'subject': lk['subject']['kind'], 'subject_text': lk['subject']['text'],
              'quantity': lk['quantity']['kind'], 'quantity_text': lk['quantity']['text']}
    if lk['subject'].get('span'):
        record['alias_span'] = lk['subject']['span']
    out.pop('reason', None)
    out.pop('abstain_code', None)
    out.update(status='bound', cell=record['cell'], number=record['number'], bindings=[record],
               binding_type=SINGLE, table_type=_table_type(p, idx), legacy_preserved=True)
    return out


# --- the two gate fixes (PREREG D11), only under v2 / v2_llm ----------------------------------------------------------
_ABLATION_V2 = re.compile(G._ABLATION_RE.pattern.replace(r"\bablat\w*", r"(?<![\w-])ablat\w*(?![\w-])"), re.I)
_SENT_V2 = re.compile(r"(?<=[.!?])(?<!\bet al\.)(?<!\bEt al\.)\s+")


def classify_table_v2(caption: str, headers: set[str] | None = None, rows: set[str] | None = None) -> str:
    """gate.classify_table, except that an ablation cue must be a standalone word ("Ablation-CAM" is a name)."""
    headers = {str(h or "") for h in headers or ()}
    rows = {str(r or "") for r in rows or ()}
    if "gate_fixes" in _off():
        return G.classify_table(caption or "", headers, rows)
    low = " ".join(filter(None, [caption or "", " ".join(sorted(headers)), " ".join(sorted(rows))])).lower()
    row_has_ablation = bool(rows) and sum(
        1 for r in rows if _ABLATION_V2.search(r) or r.strip().startswith(("-", "−", "w/o"))) >= max(2, len(rows) // 3)
    if _ABLATION_V2.search(low) or row_has_ablation:
        return "ablation"
    if G._RESULTS_RE.search(low):
        return "results"
    if G._OTHER_RE.search(low):
        return "other"
    metric_cols = sum(1 for h in headers if G._col_matches_metric(h, G._METRIC_TOKENS))
    return "results" if (metric_cols >= 1 and len(rows) >= 2) else "other"


def gate_paper_v2(record: dict[str, Any], chunks: list[dict[str, Any]], acquisition_status: str,
                  surnames: list[str]) -> dict[str, Any]:
    """gate.gate_paper with the v2 sentence split (no split after "et al."); every value goes through _gate_value."""
    sent = G._SENT if "gate_fixes" in _off() else _SENT_V2
    evidence: dict[str, list[dict[str, Any]]] = {"datasets": [], "metrics": [], "results": []}
    no_full_text = acquisition_status != G.FULL_TEXT
    for field in ("datasets", "metrics"):
        for value in G._as_list(record.get(field)):
            if no_full_text:
                it = G._evidence_item(field, value)
                it["abstain_reason"] = "no_validated_full_text"
                evidence[field].append(it)
            else:
                evidence[field].append(G._gate_value(field, value, chunks, surnames))
    results_text = record.get("results")
    if isinstance(results_text, str) and results_text.strip():
        if no_full_text:
            it = G._evidence_item("results", results_text.strip()[:300])
            it["abstain_reason"] = "no_validated_full_text"
            evidence["results"].append(it)
        else:
            for s in sent.split(results_text.strip()):
                s = s.strip()
                if len(s) < 12 or not G._NUM.search(s):
                    continue
                evidence["results"].append(G._gate_value("results", s, chunks, surnames))
    kept = [e["value"] for e in evidence["results"] if e["final"] == G.RETURNED]
    return {"datasets": [e["value"] for e in evidence["datasets"] if e["final"] == G.RETURNED],
            "metrics": [e["value"] for e in evidence["metrics"] if e["final"] == G.RETURNED],
            "results": " ".join(kept) if kept else "", "acquisition_status": acquisition_status, "evidence": evidence}
