> For research/measurement sessions, RESEARCH_DIRECTIVE.md overrides this file entirely. The UI programme below is out of scope in those sessions.

# ResearchIQ — working context

Read this file plus the one doc relevant to your task. **Do not re-read the repository.**

| Task | Read |
|---|---|
| Anything | this file |
| Backend contracts, data flow, stages | `docs/ARCHITECTURE.md` |
| Screen inventory, old→new IA mapping | `docs/UI_SPEC.md` |
| Tokens, components, motion | `docs/DESIGN_SYSTEM.md` (canonical values: root `DESIGN.md`) |
| Design-quality checkpoint before finishing a screen | `docs/IMPECCABLE_GUIDELINES.md` |

## What the product is

A **paper extraction and corpus intelligence workspace**. Not a chatbot, not a research-question
assistant. The workflow is:

```
configure extraction → extract N papers → paper grid → corpus table
   → paper analysis → corpus analysis (synthesis + gaps) → concern questions
```

The user specifies an **extraction topic**, not a question. Concern questions are an *output*
derived from the extracted corpus, never an input.

**Banned copy:** "Ask a research question", "Ask AI", "Research assistant", "Start research",
"Chat with your papers", "Explore a topic".

## Repository map

| Path | What | Status |
|---|---|---|
| `src/` | The pipeline + `src/api/main.py` (the product API, port 8000) | Frozen — do not modify without cause |
| `frontend/` | **Old vanilla UI. The functional/IA reference.** Served by `src/api/main.py` at `/` | Do not delete or break |
| `web/` | React + Vite app. Supabase auth works; its pipeline screens are the *wrong product* and are being replaced | Active work |
| `backend/` | FastAPI on port 8100 — Supabase auth + an SSE question→answer stream | **Not part of this product.** See below |
| `experiments/`, `reproducibility/` | Paper measurement programme, frozen at `paper-freeze-v1` | Do not touch |

## Hard rules

1. **Never invent data.** No fake papers, counts, citations, findings, charts or questions. If
   the backend returns nothing, render an elegant unavailable state that names the reason.
2. **Distinguish failure modes.** "No data" ≠ LLM failure ≠ timeout ≠ backend down.
3. **Do not rename or duplicate API endpoints.** The contracts in `docs/ARCHITECTURE.md` are
   what the running backend serves.
4. **Preserve every field** listed in `docs/UI_SPEC.md`. The old UI's information architecture
   is the specification.
5. **Escape backend values.** The old UI interpolates into `innerHTML`; the React rewrite must
   not reintroduce that.
6. **Candidate pool is fixed at 100** and is display-only. The backend already defaults to 100
   (`src/api/main.py` `SearchRequest`) — no backend change is needed.

## Design resources actually present

- `impeccable` skill (full reference set under `.claude/skills/impeccable/reference/`) — this is
  the design authority. A PostToolUse hook runs its detector on every UI file write.
- `design` skill (Claude Design canvas), `dataviz` skill.
- **Not available in this environment:** Figma, Canva, `Search-designs-claude`,
  `Generate-designs-claude`, `Outline-review-claude`. Do not retry them.

## Running it

```bash
uvicorn src.api.main:app --port 8000     # product API + old UI at /
cd web && npm run dev                    # React workspace, :5173
```
