# Rabarba Prompt

A local-first MVP application for LangGraph-based prompt optimization.

**What it does:** You give it a task brief (and optionally a local repo path and a target coding agent). It runs a multi-node LangGraph workflow — analyze, draft, assess risk, assemble, review, refine — and returns a fully structured, risk-annotated implementation prompt ready to paste into Cursor, Claude Code, or any other coding agent.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- API keys for Anthropic and OpenAI

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env
```

**Edit `backend/.env`** and fill in your API keys:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

> **Note:** The `.env` file lives in `backend/` — this is where the backend reads model and provider configuration. Do not place it in the project root for the backend to pick it up.

Start the server:

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

### 2. Frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Using the App

1. **Task Brief** (required) — describe what you want to build. Include language, framework, constraints, and expected output. The more detail, the better the optimizer performs.
2. **Local Repo Path** (optional) — point to a local project folder (e.g. `/Users/you/myproject`). The scanner reads file structure, package files, and entry points — no code is uploaded anywhere.
3. **Target Agent** — choose Generic, Cursor, or Claude Code. This tailors the prompt format.
4. **Max Iterations** — 1–5. Default 3. Each iteration is one full review cycle. More iterations = more refinement, more API cost.

Click **Optimize Prompt**. The workflow typically takes 30–120 seconds depending on iteration count.

---

## LLM Provider Mapping

| Node | Provider | Model |
|------|----------|-------|
| Input Analyzer | Anthropic | `ANTHROPIC_MODEL` |
| Drafter | Anthropic | `ANTHROPIC_MODEL` |
| Risk Assessor | Anthropic | `ANTHROPIC_MODEL` |
| Reviewer | OpenAI | `OPENAI_MODEL` |
| Refiner | Anthropic | `ANTHROPIC_MODEL` |

Reviewer intentionally uses a different vendor to reduce same-model confirmation bias.

Defaults: `ANTHROPIC_MODEL=claude-sonnet-4-5`, `OPENAI_MODEL=gpt-4o-mini`.

> If `claude-sonnet-4-5` is not yet available on your API tier, set `ANTHROPIC_MODEL=claude-3-5-sonnet-20241022` (or another available Claude model) in `backend/.env`.

---

## Workflow

```
Task Brief + optional repo_path
→ Repo Scanner         (no LLM — lightweight heuristics)
→ Input Analyzer       (Anthropic)
→ Drafter              (Anthropic)
→ Risk Assessor        (Anthropic)
→ Prompt Assembler     (deterministic Python — no LLM)
→ Reviewer             (OpenAI — different vendor by design)
→ Stop Logic           (pure Python)
→ Refiner              (Anthropic, if stop=False)
→ Risk Assessor        (always re-runs after Refiner)
→ Prompt Assembler     (always re-runs after Refiner)
→ Reviewer
→ Stop Logic
→ ... until stop condition
```

**Stop conditions (priority order):**
1. `all_pass` — all rubric items are PASS
2. `repeated_fail` — same fail signature two iterations in a row
3. `max_iterations` — iteration limit reached
4. `uncertain_only` — no FAILs, only UNCERTAINs caused by missing context info
5. `error` — any node raised an exception (graceful, returns partial state)

---

## Extension Points

The codebase is structured for future growth without a rewrite.

### GitHub Scanner
Implement `GitHubRepoScanner(BaseRepoScanner)` in:
```
backend/app/graph/services/repo_scanner/github_scanner.py
```
It already exists as a documented stub. Extend `BaseRepoScanner.scan()` to accept a GitHub URL or `owner/repo` string instead of a local path, then instantiate it in the `repo_scanner` node based on the input format.

### SQLite Persistence
Implement in:
```
backend/app/graph/services/persistence.py
```
The stub already has `save_run(run_id, state)` and `load_run(run_id)`. The `run_id` (UUID) is already in `PromptOptimizerState` and set at the start of every run. Call `save_run()` at the end of `routes.py` after `graph.invoke()` completes.

### Multi-User Support
- `run_id` is already in state as an extension point
- Add `user_id` to `PromptOptimizerState` alongside it
- Pass a user token in the API request; decode it in the route handler
- The persistence layer naturally maps `run_id` → user runs

### Model Swapping
Change `ANTHROPIC_MODEL` or `OPENAI_MODEL` in `backend/.env` — no code changes needed. The provider services read from config at startup.

---

## Project Structure

```
rabarba-prompt/
├── .env.example
├── pyproject.toml
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── main.py                        # uvicorn entry point
│   └── app/
│       ├── api/routes.py              # POST /api/optimize, GET /api/health
│       ├── core/config.py             # env-based config
│       └── graph/
│           ├── graph.py               # LangGraph wiring + loop
│           ├── state.py               # all schemas + PromptOptimizerState
│           ├── nodes/                 # one file per node
│           ├── prompts/system_prompts.py
│           └── services/
│               ├── llm/               # Anthropic + OpenAI providers
│               ├── repo_scanner/      # LocalRepoScanner + GitHub stub
│               └── persistence.py    # SQLite extension point stub
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── lib/api.ts                 # typed fetch wrapper
        └── components/               # OptimizeForm, ResultPanel, etc.
```

---

## API

### `POST /api/optimize`

```json
{
  "task_brief": "string (required, non-empty)",
  "repo_path": "string | null",
  "target_agent": "Generic | Cursor | Claude Code | null",
  "max_iterations": 3
}
```

Response always returns 200. On workflow error: `stop_reason: "error"`, `last_error: "<message>"`.

### `GET /api/health`

```json
{ "status": "ok" }
```
