# src/coding_agent/graph/graph.py

from langgraph.graph import StateGraph, END

from coding_agent.graph.state import GraphState
from coding_agent.graph.router import route_from_tester, route_from_reviewer
from coding_agent.nodes.planner import planner_node
from coding_agent.nodes.coder import coder_node
from coding_agent.nodes.tester import tester_node
from coding_agent.nodes.reviewer import reviewer_node
from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


def build_graph() -> StateGraph:
    """
    Builds and compiles the LangGraph StateGraph.

    Flow:
        planner → coder → tester →(conditional)→ reviewer / coder / planner
        reviewer →(conditional)→ tester / coder(next_item) / END
    """
    graph = StateGraph(GraphState)

    # ── Register nodes ─────────────────────────────────────────────────────
    graph.add_node("planner",  planner_node)
    graph.add_node("coder",    coder_node)
    graph.add_node("tester",   tester_node)
    graph.add_node("reviewer", reviewer_node)

    # ── Entry point ────────────────────────────────────────────────────────
    graph.set_entry_point("planner")

    # ── Fixed edges ────────────────────────────────────────────────────────
    graph.add_edge("planner", "coder")
    graph.add_edge("coder",   "tester")

    # ── Conditional edges from Tester ──────────────────────────────────────
    graph.add_conditional_edges(
        "tester",
        route_from_tester,
        {
            "reviewer": "reviewer",
            "coder":    "coder",
            "planner":  "planner",
        }
    )

    # ── Conditional edges from Reviewer ────────────────────────────────────
    graph.add_conditional_edges(
        "reviewer",
        route_from_reviewer,
        {
            "tester":    "tester",
            "next_item": "coder",   # approved, advance to next plan item
            "end":       END,
        }
    )

    logger.info("Graph compiled successfully.")
    return graph.compile()


# ── Compiled graph instance ────────────────────────────────────────────────────
coding_agent_graph = build_graph()