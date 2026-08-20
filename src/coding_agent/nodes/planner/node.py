# src/coding_agent/nodes/planner/node.py

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from coding_agent.graph.state import GraphState
from coding_agent.core.config import settings
from coding_agent.core.log_manager import get_logger
from coding_agent.nodes.planner.prompts import (
    PLANNER_INITIAL_PROMPT,
    PLANNER_SUB_PROMPT,
)
from coding_agent.nodes.planner.helpers import (
    parse_plan_items,
    format_plan_for_prompt,
)

logger = get_logger(__name__)


def planner_node(state: GraphState) -> GraphState:
    """
    Planner node — single LLM call, no tools, no loop.

    Initial mode  : breaks raw task into ordered PlanItems → state["plan"]
    Sub-plan mode : creates fix plan from test failures  → state["sub_plan"]

    Routing after this node is always "coder" unless parsing fails.
    """
    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.model_name,
    )

    # ── Detect mode ───────────────────────────────────────────────────────────
    is_sub_planning = (
        state.get("routing_decision") == "planner"
        and state.get("test_results") is not None
    )

    # ── Build prompt ──────────────────────────────────────────────────────────
    if is_sub_planning:
        logger.info("Planner: sub-plan mode")
        system_prompt = PLANNER_SUB_PROMPT.format(
            plan=format_plan_for_prompt(state.get("plan", [])),
            test_results=state["test_results"],
        )
        human_message = "Create a sub-plan to fix only the failing tests above."

    else:
        logger.info("Planner: initial mode")
        system_prompt = PLANNER_INITIAL_PROMPT.format(
            task=state["task"],
        )
        human_message = state["task"]

    # ── Call LLM ──────────────────────────────────────────────────────────────
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_message),
    ])

    logger.debug(f"Planner raw response: {response.content[:300]}")

    # ── Parse response ────────────────────────────────────────────────────────
    items = parse_plan_items(response.content)

    if not items:
        logger.error("Planner produced no items. Terminating graph.")
        return {
            **state,
            "routing_decision": "end",
        }

    # ── Update state ──────────────────────────────────────────────────────────
    if is_sub_planning:
        logger.info(f"Sub-plan created: {len(items)} items")
        return {
            **state,
            "sub_plan": items,
            "current_plan": "sub",
            "current_item_index": 0,
            "routing_decision": "coder",
        }

    else:
        logger.info(f"Initial plan created: {len(items)} items")
        return {
            **state,
            "plan": items,
            "sub_plan": [],
            "current_plan": "main",
            "current_item_index": 0,
            "routing_decision": "coder",
        }