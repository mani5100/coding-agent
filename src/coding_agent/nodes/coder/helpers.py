# src/coding_agent/nodes/coder/helpers.py

from coding_agent.graph.state import GraphState, PlanItem
from coding_agent.core.log_manager import get_logger
from coding_agent.nodes.planner.helpers import (
    get_current_plan_item,
    format_plan_for_prompt,
)

logger = get_logger(__name__)


def format_carry_on_context(state: GraphState) -> str:
    """
    Builds the shared context block injected into every node.
    Gives the agent full awareness of the overall plan and what has been done.
    """
    lines = []

    # ── Overall Plan ──────────────────────────────────────────────────────────
    lines.append("## Overall Plan")
    plan = state.get("plan", [])
    if plan:
        lines.append(format_plan_for_prompt(plan))
    else:
        lines.append("No plan available yet.")
    lines.append("")

    # ── Sub Plan (if active) ──────────────────────────────────────────────────
    sub_plan = state.get("sub_plan", [])
    if sub_plan:
        lines.append("## Active Sub Plan (Fix)")
        lines.append(format_plan_for_prompt(sub_plan))
        lines.append("")

    # ── Current Item ──────────────────────────────────────────────────────────
    lines.append("## Current Item")
    current_item = get_current_plan_item(state)
    if current_item:
        lines.append(f"ID    : {current_item.id}")
        lines.append(f"Title : {current_item.title}")
        lines.append(f"Desc  : {current_item.description}")
        lines.append(f"Done when: {current_item.acceptance_criteria}")
    else:
        lines.append("No current item.")
    lines.append("")

    # ── Completed Work ────────────────────────────────────────────────────────
    lines.append("## Completed Work")
    completed = state.get("completed_items", [])
    if completed:
        for item in completed:
            lines.append(f"- [{item.id}] {item.title}")
    else:
        lines.append("Nothing completed yet.")
    lines.append("")

    # ── Latest Test Results ───────────────────────────────────────────────────
    lines.append("## Latest Test Results")
    test_results = state.get("test_results")
    if test_results:
        lines.append(test_results)
    else:
        lines.append("No test results yet.")

    return "\n".join(lines)


def build_task_from_plan_item(state: GraphState) -> str | None:
    """
    Builds the full task string passed to run_agent().
    Combines current PlanItem details with the carry-on context block.
    Returns None if no current item exists.
    """
    current_item = get_current_plan_item(state)

    if current_item is None:
        logger.error("build_task_from_plan_item: no current item found in state")
        return None

    lines = []

    # ── Current Task ──────────────────────────────────────────────────────────
    lines.append("[CURRENT TASK]")
    lines.append(f"Title              : {current_item.title}")
    lines.append(f"Description        : {current_item.description}")
    lines.append(f"Acceptance Criteria: {current_item.acceptance_criteria}")
    lines.append("")

    # ── Project Context ───────────────────────────────────────────────────────
    lines.append("[PROJECT CONTEXT]")
    lines.append(format_carry_on_context(state))

    task_str = "\n".join(lines)
    logger.debug(f"Built task string ({len(task_str)} chars) for item: {current_item.id}")

    return task_str