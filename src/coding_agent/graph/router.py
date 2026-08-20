from coding_agent.graph.state import GraphState
from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


def route_from_tester(state: GraphState) -> str:
    """
    Called by LangGraph after Tester node finishes.

    Valid returns:
        "coder"    → small fix, Coder handles directly
        "planner"  → feature broken, Planner creates sub-plan
        "reviewer" → all tests passed
    """
    decision = state["routing_decision"]
    logger.info(f"Tester routing decision: {decision}")

    if decision not in ("coder", "planner", "reviewer"):
        logger.warning(f"Unknown routing from Tester: {decision}. Defaulting to reviewer.")
        return "reviewer"

    return decision


def route_from_reviewer(state: GraphState) -> str:
    """
    Called by LangGraph after Reviewer node finishes.

    Valid returns:
        "tester"    → issues found, re-test
        "next_item" → approved, move to next plan item (maps to coder in graph)
        "end"       → all items approved, terminate
    """
    decision = state["routing_decision"]
    logger.info(f"Reviewer routing decision: {decision}")

    if decision not in ("tester", "next_item", "end"):
        logger.warning(f"Unknown routing from Reviewer: {decision}. Defaulting to end.")
        return "end"

    return decision