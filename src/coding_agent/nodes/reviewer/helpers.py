from typing import Literal
from pydantic import BaseModel

from coding_agent.graph.state import GraphState
from coding_agent.core.log_manager import get_logger
from coding_agent.nodes.planner.helpers import (
    get_current_plan_item,
    format_plan_for_prompt,
)

logger = get_logger(__name__)


# ── Reviewer Verdict Schema ───────────────────────────────────────────────────

class ReviewerVerdict(BaseModel):
    """
    Structured output schema for the Reviewer verdict call.
    Used with llm.with_structured_output(ReviewerVerdict).
    """
    verdict: Literal["approved", "rejected"]
    routing_decision: Literal["tester", "next_item", "end"]
    reason: str
    issues_found: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def format_plan_progress(state: GraphState) -> str:
    """
    Formats current plan progress for injection into REVIEWER_VERDICT_PROMPT.
    Shows total, completed, remaining, and whether this is the last item.
    """
    current_plan_key = state.get("current_plan", "main")
    plan = state.get("plan", []) if current_plan_key == "main" else state.get("sub_plan", [])
    current_index = state.get("current_item_index", 0)

    # current_item_index was already incremented by coder_node
    # so items before current_index are done
    total = len(plan)
    completed = min(current_index, total)
    remaining = max(total - current_index, 0)

    current_item = get_current_plan_item(state)
    current_label = (
        f"{current_item.id}: {current_item.title}"
        if current_item else "None (all items completed)"
    )

    lines = [
        f"Total items  : {total}",
        f"Completed    : {completed}",
        f"Remaining    : {remaining}",
        f"Current item : {current_label}",
        f"Last item    : {'YES' if is_last_item(state) else 'NO'}",
    ]

    return "\n".join(lines)


def format_task_docs(task_docs: list[str]) -> str:
    """
    Joins accumulated per-item docs with clear separators.
    Used for injection into REVIEWER_FINAL_PROMPT.
    """
    if not task_docs:
        return "No documentation available yet."

    sections = []
    for i, doc in enumerate(task_docs, start=1):
        sections.append(f"=== Item {i} ===")
        sections.append(doc.strip())
        sections.append("")

    return "\n".join(sections).strip()


def is_last_item(state: GraphState) -> bool:
    current_plan_key = state.get("current_plan", "main")
    plan = state.get("plan", []) if current_plan_key == "main" else state.get("sub_plan", [])
    if not plan:
        return True
    current_index = state.get("current_item_index", 0)
    # Last item when index points to the last element
    return current_index >= len(plan) - 1