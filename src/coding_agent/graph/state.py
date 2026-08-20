# src/coding_agent/graph/state.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TypedDict, Optional


# ── Plan Item ─────────────────────────────────────────────────────────────────

@dataclass
class PlanItem:
    id: str
    title: str
    description: str
    acceptance_criteria: str
    status: str = "pending"          # pending | in_progress | done | failed
    depends_on: list[str] = field(default_factory=list)


# ── Graph State ───────────────────────────────────────────────────────────────

class GraphState(TypedDict):

    # ── Task ──────────────────────────────────────────────────────────────────
    task: str
    working_dir: str
    session_id: str

    # ── Plan ──────────────────────────────────────────────────────────────────
    plan: list[PlanItem]
    sub_plan: list[PlanItem]
    current_plan: str                # "main" | "sub"
    current_item_index: int

    # ── Outputs ───────────────────────────────────────────────────────────────
    code_output: Optional[str]
    test_results: Optional[str]
    review_output: Optional[str]

    # ── Documentation ─────────────────────────────────────────────────────────
    task_docs: list[str]
    final_doc: Optional[str]

    # ── Routing ───────────────────────────────────────────────────────────────
    routing_decision: str
    iteration: int
    max_iterations: int
    
    log_path: str