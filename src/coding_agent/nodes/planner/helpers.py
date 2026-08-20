# src/coding_agent/nodes/planner/helpers.py

import json
import uuid

from coding_agent.graph.state import GraphState, PlanItem
from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


def parse_plan_items(raw: str) -> list[PlanItem]:
    """
    Parse raw LLM string output into a list of PlanItem objects.
    Strips markdown fences, parses JSON, converts dicts to PlanItems.
    Returns empty list on any failure.
    """
    try:
        # Strip accidental markdown fences
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            clean = "\n".join(lines).strip()

        items = json.loads(clean)

        if not isinstance(items, list):
            logger.error(f"Expected JSON array, got: {type(items)}")
            return []

        plan_items = []
        for item in items:
            if not isinstance(item, dict):
                logger.warning(f"Skipping non-dict item: {item}")
                continue

            if "title" not in item or "description" not in item:
                logger.warning(f"Skipping item missing required fields: {item}")
                continue

            plan_items.append(PlanItem(
                id=item.get("id", f"item_{uuid.uuid4().hex[:6]}"),
                title=item["title"],
                description=item["description"],
                acceptance_criteria=item.get("acceptance_criteria", ""),
                status="pending",
                depends_on=item.get("depends_on", []),
            ))

        logger.info(f"Parsed {len(plan_items)} plan items successfully")
        return plan_items

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed: {e}\nRaw output:\n{raw[:500]}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing plan items: {e}")
        return []


def format_plan_for_prompt(plan: list[PlanItem]) -> str:
    """
    Format a list of PlanItems into a readable string for prompt injection.
    Shows status of each item so LLM knows what is done and what failed.
    """
    if not plan:
        return "No plan items."

    lines = []
    for item in plan:
        status_label = item.status.upper()
        lines.append(f"[{status_label}] {item.id}: {item.title}")
        lines.append(f"  Description       : {item.description}")
        lines.append(f"  Acceptance Criteria: {item.acceptance_criteria}")
        if item.depends_on:
            lines.append(f"  Depends On        : {', '.join(item.depends_on)}")
        lines.append("")

    return "\n".join(lines).strip()


def get_current_plan_item(state: GraphState) -> PlanItem | None:
    """
    Returns the current PlanItem based on current_plan and current_item_index.
    Returns None if index is out of bounds or plan is empty.
    """
    current_plan = state.get("current_plan", "main")
    index = state.get("current_item_index", 0)

    plan = state.get("plan", []) if current_plan == "main" else state.get("sub_plan", [])

    if not plan:
        logger.warning(f"Plan is empty for current_plan='{current_plan}'")
        return None

    if index >= len(plan):
        logger.warning(f"Index {index} out of bounds for plan of length {len(plan)}")
        return None

    return plan[index]