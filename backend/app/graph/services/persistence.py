"""
SQLite persistence service for Rabarba Prompt.

Design rules:
  - Each DB operation opens its own sqlite3.connect() — no shared connections.
  - init_db() is idempotent and called at application startup (main.py).
  - save_run_artifacts() is the only place prompt_versions and node_usage are committed.
  - Persistence failures must never block the API response; callers wrap in try/except.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.api.schemas import PromptVersionOut, RunSummary
    from app.graph.state import NodeUsage

DB_PATH = Path(__file__).parent.parent.parent.parent / "runs.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id       TEXT PRIMARY KEY,
  status       TEXT NOT NULL DEFAULT 'pending',
  task_brief   TEXT NOT NULL,
  config       TEXT NOT NULL,
  intro_data   TEXT,
  result_json  TEXT,
  stop_reason  TEXT,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_versions (
  run_id           TEXT NOT NULL,
  iteration        INTEGER NOT NULL,
  source           TEXT NOT NULL DEFAULT 'assembled',
  prompt_text      TEXT NOT NULL,
  fail_signature   TEXT NOT NULL DEFAULT '',
  reviewer_verdict TEXT NOT NULL DEFAULT '',
  is_stable        INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT NOT NULL,
  PRIMARY KEY (run_id, iteration),
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS node_usage (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT NOT NULL,
  node_name     TEXT NOT NULL,
  iteration     INTEGER NOT NULL DEFAULT 0,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd      REAL NOT NULL DEFAULT 0.0,
  duration_ms   INTEGER NOT NULL DEFAULT 0,
  model         TEXT NOT NULL,
  vendor        TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_status    ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created   ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_node_usage_run ON node_usage(run_id);
CREATE INDEX IF NOT EXISTS idx_pv_run         ON prompt_versions(run_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def init_db() -> None:
    """Create runs.db and all tables. Idempotent — safe to call on every startup."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_SCHEMA_SQL)


def create_run(run_id: str, task_brief: str, config: dict) -> None:
    """Insert a new run row with status=pending."""
    now = _now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO runs (run_id, status, task_brief, config, created_at, updated_at)
            VALUES (?, 'pending', ?, ?, ?, ?)
            """,
            (run_id, task_brief, json.dumps(config), now, now),
        )


def update_run_status(
    run_id: str,
    status: str,
    stop_reason: Optional[str] = None,
) -> None:
    """Update status (and optionally stop_reason) for a run."""
    now = _now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE runs
            SET status = ?, stop_reason = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (status, stop_reason, now, run_id),
        )


def save_run_artifacts(
    run_id: str,
    prompt_versions: list["PromptVersionOut"],
    node_usages: list["NodeUsage"],
) -> None:
    """
    Write prompt_versions and node_usage rows in a single transaction.
    This is the only place these tables are written — no partial commits elsewhere.
    """
    now = _now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        for pv in prompt_versions:
            conn.execute(
                """
                INSERT OR REPLACE INTO prompt_versions
                  (run_id, iteration, source, prompt_text,
                   fail_signature, reviewer_verdict, is_stable, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    pv.iteration,
                    pv.source,
                    pv.prompt_text,
                    pv.fail_signature,
                    pv.reviewer_verdict,
                    1 if pv.is_stable else 0,
                    pv.created_at,
                ),
            )
        for u in node_usages:
            conn.execute(
                """
                INSERT INTO node_usage
                  (run_id, node_name, iteration, input_tokens, output_tokens,
                   cost_usd, duration_ms, model, vendor, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    u.node_name,
                    u.iteration,
                    u.input_tokens,
                    u.output_tokens,
                    u.cost_usd,
                    u.duration_ms,
                    u.model,
                    u.vendor,
                    now,
                ),
            )


def save_result(run_id: str, result: object) -> None:
    """
    Serialize result via model_dump_json() and write to result_json column.
    Only called when stop_reason != "error".
    """
    now = _now_iso()
    result_json = result.model_dump_json()  # type: ignore[attr-defined]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE runs SET result_json = ?, updated_at = ? WHERE run_id = ?",
            (result_json, now, run_id),
        )


def load_run(run_id: str) -> Optional[dict]:
    """Return the runs row as a dict, or None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    return dict(row) if row else None


def list_runs(limit: int = 50) -> list["RunSummary"]:
    """
    Return the most recent runs ordered by created_at DESC.
    Uses CTEs to avoid row multiplication when joining prompt_versions + node_usage.
    """
    from app.api.schemas import RunSummary

    sql = """
    WITH pv_counts AS (
      SELECT run_id, COUNT(*) AS iteration_count
      FROM prompt_versions
      GROUP BY run_id
    ),
    nu_costs AS (
      SELECT run_id, SUM(cost_usd) AS total_cost_usd
      FROM node_usage
      GROUP BY run_id
    )
    SELECT
      r.run_id,
      r.status,
      r.stop_reason,
      r.task_brief,
      r.created_at,
      r.updated_at,
      COALESCE(pv.iteration_count, 0) AS iteration_count,
      COALESCE(nu.total_cost_usd, 0.0) AS total_cost_usd
    FROM runs r
    LEFT JOIN pv_counts pv ON r.run_id = pv.run_id
    LEFT JOIN nu_costs  nu ON r.run_id = nu.run_id
    ORDER BY r.created_at DESC
    LIMIT ?
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, (limit,)).fetchall()

    result = []
    for row in rows:
        result.append(
            RunSummary(
                run_id=row["run_id"],
                status=row["status"],
                stop_reason=row["stop_reason"],
                task_brief_preview=row["task_brief"][:80],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                iteration_count=row["iteration_count"],
                total_cost_usd=row["total_cost_usd"],
            )
        )
    return result


def load_run_detail(run_id: str) -> Optional[dict]:
    """
    Load full run detail including prompt_versions and cost_summary.
    Returns None if run not found.
    """
    from app.api.schemas import (
        CostSummary,
        NodeCostSummary,
        PromptVersionOut,
    )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        run_row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run_row is None:
            return None

        pv_rows = conn.execute(
            """
            SELECT iteration, source, prompt_text, fail_signature,
                   reviewer_verdict, is_stable, created_at
            FROM prompt_versions
            WHERE run_id = ?
            ORDER BY iteration ASC
            """,
            (run_id,),
        ).fetchall()

        nu_rows = conn.execute(
            """
            SELECT node_name, iteration, input_tokens, output_tokens,
                   cost_usd, duration_ms, model, vendor
            FROM node_usage
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()

    run = dict(run_row)
    config = json.loads(run.get("config") or "{}")
    result_json_raw = run.get("result_json")
    final_result = json.loads(result_json_raw) if result_json_raw else None

    prompt_versions = [
        PromptVersionOut(
            run_id=run_id,
            iteration=r["iteration"],
            source=r["source"],
            prompt_text=r["prompt_text"],
            fail_signature=r["fail_signature"],
            reviewer_verdict=r["reviewer_verdict"],
            is_stable=bool(r["is_stable"]),
            created_at=r["created_at"],
        )
        for r in pv_rows
    ]

    # Aggregate cost by node
    from collections import defaultdict
    by_node: dict[str, list] = defaultdict(list)
    for r in nu_rows:
        by_node[r["node_name"]].append(r)

    node_summaries = [
        NodeCostSummary(
            node_name=name,
            call_count=len(usages),
            total_cost_usd=sum(u["cost_usd"] for u in usages),
            total_input_tokens=sum(u["input_tokens"] for u in usages),
            total_output_tokens=sum(u["output_tokens"] for u in usages),
        )
        for name, usages in by_node.items()
    ]
    cost_summary = CostSummary(
        total_cost_usd=sum(s.total_cost_usd for s in node_summaries),
        total_input_tokens=sum(s.total_input_tokens for s in node_summaries),
        total_output_tokens=sum(s.total_output_tokens for s in node_summaries),
        by_node=node_summaries,
    )

    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "stop_reason": run.get("stop_reason"),
        "task_brief": run["task_brief"],
        "config": config,
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "prompt_versions": prompt_versions,
        "cost_summary": cost_summary,
        "final_result": final_result,
    }
