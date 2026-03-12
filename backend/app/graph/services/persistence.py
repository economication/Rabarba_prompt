"""
Persistence service stub.

EXTENSION POINT: persist run to SQLite here.
When implementing:
  1. Create a SQLite database (e.g. runs.db) with a `runs` table
  2. Map PromptOptimizerState fields to columns / JSON blob
  3. Use run_id (UUID already in state) as the primary key
  4. Add user_id column alongside run_id for multi-user support
  5. Call save_run() at the end of the graph execution in routes.py

For multi-user support:
  - run_id is already in PromptOptimizerState as an extension point
  - Add user_id to the state schema when needed
  - The API request can carry a user token; decode it in the route handler
"""

from __future__ import annotations  # Python 3.9 compat

from typing import Any


def save_run(run_id: str, state: dict[str, Any]) -> None:
    # TODO: persist run_id + state to SQLite
    pass


def load_run(run_id: str) -> dict[str, Any] | None:
    # TODO: load run from SQLite by run_id
    return None
