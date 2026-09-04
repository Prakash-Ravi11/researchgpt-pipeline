"""arXiv e-print (LaTeX source) retrieval — Stage 1, stdlib only.

HTTP GET + stdlib tarfile/gzip. No new dependency, no Docling/Marker/GROBID/Java.
Requests are throttled to one per 3 s (arXiv throttles e-print aggressively).

This module supplies CONTENT ONLY. Identity + metadata are never read from here
(S2ORC: author-defined LaTeX metadata is worse than PDF-derived and was excluded
from their paper matching). See acquire.identity_validate.
"""
from __future__ import annotations

import gzip
import io
import re
import tarfile
import threading
import time
from typing import Any

EPRINT_URL = "https://arxiv.org/e-print/{arxiv_id}"
_MIN_INTERVAL_S = 3.0
_last_call = [0.0]
_lock = threading.Lock()

_MAX_TEX_BYTES = 8_000_000          # concatenated resolved source cap
_CAP_HINT = 38_000_000             # ~ acquire.FETCH_CAP_BYTES: at/above this the
                                   # archive is truncated and unrecoverable -> PDF fallback
_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")
_DOCCLASS_RE = re.compile(r"\\documentclass[^\n]*")
_BEGINDOC_RE = re.compile(r"\\begin\s*\{document\}")


def _throttle() -> None:
    with _lock:
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def eprint_url(arxiv_id: str) -> str:
    return EPRINT_URL.format(arxiv_id=str(arxiv_id).strip())


def _members(body: bytes) -> dict[str, bytes] | None:
    """Return {name: bytes} for every .tex in the e-print, or None if the payload
    is not a usable LaTeX source bundle (PDF-only submission, HTML error, or a
    truncated/corrupt archive — `acquire.fetch` caps bytes, so a huge e-print
    comes back truncated and must be treated as 'no source', not an error)."""
    # arXiv e-prints are a tar (often .tar.gz), a lone gzipped .tex, or a bare PDF.
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:*") as tf:
            out: dict[str, bytes] = {}
            for m in tf.getmembers():
                if not m.isfile() or m.size > _MAX_TEX_BYTES:
                    continue
                low = m.name.lower()
                if low.endswith((".tex", ".ltx")) or ("." not in low.split("/")[-1]):
                    f = tf.extractfile(m)
                    if f is not None:
                        out[m.name] = f.read()
            return out or None
    except (tarfile.TarError, EOFError, OSError, Exception):  # noqa: BLE001
        # truncated tar.gz (byte cap), zlib error, odd member — fall through /
        # give up rather than propagate into the acquisition loop.
        pass
    # not a (readable) tar: try lone gzip
    try:
        raw = gzip.decompress(body)
    except (OSError, EOFError, Exception):  # noqa: BLE001
        raw = body
    if raw[:5] == b"%PDF-":
        return None                        # PDF-only submission — no LaTeX source
    if b"\\documentclass" in raw[:20000] or b"\\begin{document}" in raw[:20000]:
        return {"main.tex": raw}
    return None


def _decode(b: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def _pick_main(files: dict[str, bytes]) -> str | None:
    scored = []
    for name, b in files.items():
        s = _decode(b)
        score = 0
        if _DOCCLASS_RE.search(s):
            score += 5
        if _BEGINDOC_RE.search(s):
            score += 5
        score += s.count("\\section") * 0.1
        if score:
            scored.append((score, len(s), name))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]


def _resolve_inputs(main_name: str, files: dict[str, bytes], _depth: int = 0,
                    _seen: set[str] | None = None) -> str:
    """Inline \\input / \\include targets (recursively, cycle- and depth-guarded)."""
    _seen = _seen if _seen is not None else set()
    if _depth > 12 or main_name in _seen:
        return ""
    _seen.add(main_name)
    src = _decode(files.get(main_name, b""))

    # index files by basename without extension for tolerant matching
    by_key: dict[str, str] = {}
    for n in files:
        key = n.rsplit("/", 1)[-1]
        by_key.setdefault(key.lower(), n)
        if key.lower().endswith((".tex", ".ltx")):
            by_key.setdefault(key.rsplit(".", 1)[0].lower(), n)

    def repl(m: re.Match) -> str:
        target = m.group(1).strip().strip('"')
        cands = [target, target + ".tex", target + ".ltx",
                 target.rsplit("/", 1)[-1], target.rsplit("/", 1)[-1] + ".tex"]
        for c in cands:
            hit = files.get(c) and c or by_key.get(c.lower())
            if hit:
                return "\n" + _resolve_inputs(hit, files, _depth + 1, _seen) + "\n"
        return ""              # unresolved \input — drop it, parser tolerates gaps

    return _INPUT_RE.sub(repl, src)


def fetch_eprint_latex(arxiv_id: str, fetch_fn) -> dict[str, Any]:
    """Download + assemble the resolved LaTeX source for `arxiv_id`.

    `fetch_fn` is acquire.fetch (single choke point for the byte cap + UA), so
    this module issues no HTTP of its own beyond delegating to it — after the
    3 s throttle.

    Returns {ok, reason, latex, n_tex_files, main, bytes, http_status}.
    """
    def _fail(reason: str, r: dict | None = None) -> dict[str, Any]:
        return {"ok": False, "reason": reason, "latex": "", "n_tex_files": 0, "main": None,
                "bytes": (r or {}).get("bytes"), "http_status": (r or {}).get("http_status")}

    _throttle()
    try:
        r = fetch_fn(eprint_url(arxiv_id))
    except Exception as exc:  # noqa: BLE001 — never propagate into the acquisition loop
        return _fail(f"eprint_fetch_exception:{type(exc).__name__}")
    if not r.get("ok") or (r.get("http_status") or 500) >= 400:
        return _fail(f"eprint_fetch_failed:{r.get('error') or r.get('http_status')}", r)
    # `acquire.fetch` stops at its byte cap; a truncated archive is unrecoverable
    # → treat as "no source" and let the paper fall back to the arXiv PDF.
    if (r.get("bytes") or 0) >= _CAP_HINT:
        return _fail("eprint_exceeds_fetch_cap", r)
    try:
        files = _members(r["body"])
        if not files:
            return _fail("no_latex_source_in_eprint", r)
        main = _pick_main(files)
        if main is None:
            blob = "\n".join(_decode(b) for b in files.values())[:_MAX_TEX_BYTES]
            return {"ok": bool(blob.strip()),
                    "reason": "ok_no_main_concatenated" if blob.strip() else "empty_latex",
                    "latex": blob, "n_tex_files": len(files), "main": None,
                    "bytes": r.get("bytes"), "http_status": r.get("http_status")}
        latex = _resolve_inputs(main, files)[:_MAX_TEX_BYTES]
    except Exception as exc:  # noqa: BLE001
        return _fail(f"eprint_parse_error:{type(exc).__name__}", r)
    return {"ok": bool(latex.strip()), "reason": "ok" if latex.strip() else "empty_latex",
            "latex": latex, "n_tex_files": len(files), "main": main,
            "bytes": r.get("bytes"), "http_status": r.get("http_status")}
