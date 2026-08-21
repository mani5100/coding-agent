# src/coding_agent/nodes/reviewer/node.py

import json
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from coding_agent.graph.state import GraphState
from coding_agent.core.config import settings
from coding_agent.core.log_manager import get_logger
from coding_agent.nodes.planner.helpers import (
    get_current_plan_item,
    format_plan_for_prompt,
)
from coding_agent.nodes.reviewer.prompts import (
    REVIEWER_ITEM_PROMPT,
    REVIEWER_VERDICT_PROMPT,
    REVIEWER_FINAL_PROMPT,
)
from coding_agent.nodes.reviewer.helpers import (
    ReviewerVerdict,
    format_plan_progress,
    format_task_docs,
    is_last_item,
)
from coding_agent.tools.read_file import read_file
from coding_agent.tools.write_file import write_file
from coding_agent.tools.shell_exec import shell_exec

logger = get_logger(__name__)

MAX_REVIEWER_ITERATIONS = 100

# ── Tools ─────────────────────────────────────────────────────────────────────

REVIEWER_TOOLS = [read_file, write_file, shell_exec]
REVIEWER_TOOL_MAP = {t.name: t for t in REVIEWER_TOOLS}


# ── Phase 1 — Review Loop ─────────────────────────────────────────────────────

def _run_review_loop(
    state: GraphState,
    llm_with_tools,
    current_item,
) -> tuple[str, str]:
    """
    Mini agent loop for reviewing the current item.
    LLM reads source files, verifies acceptance criteria,
    writes per-item documentation.

    Returns:
        (review_findings, item_doc) — both as strings
    """
    working_dir = state.get("working_dir", "/workspace")

    system_prompt = REVIEWER_ITEM_PROMPT.format(
        item_id=current_item.id,
        item_title=current_item.title,
        item_description=current_item.description,
        acceptance_criteria=current_item.acceptance_criteria,
        test_results=state.get("test_results") or "No test results available.",
        code_output=state.get("code_output") or "No code output available.",
        working_dir=settings.container_workdir,
    )

    messages = [
        HumanMessage(content=f"Review the implementation of: {current_item.title}")
    ]

    review_findings = ""
    item_doc = ""

    for iteration in range(1, MAX_REVIEWER_ITERATIONS + 1):
        logger.info(f"Reviewer loop iteration {iteration}/{MAX_REVIEWER_ITERATIONS}")

        response: AIMessage = llm_with_tools.invoke(
            [SystemMessage(content=system_prompt)] + messages
        )
        messages.append(response)

        content = response.content or ""
        logger.debug(f"Reviewer LLM: {content[:200] or '[no content]'}")

        # ── Capture review text ────────────────────────────────────────────
        if content:
            review_findings += f"\n{content}"

            # Extract documentation section
            if "## " in content:
                item_doc = content

        # ── Exit signal ────────────────────────────────────────────────────
        if "REVIEW_DONE" in content.upper():
            logger.info("Reviewer: REVIEW_DONE signal received.")
            break

        # ── No tool calls ──────────────────────────────────────────────────
        if not response.tool_calls:
            logger.warning("Reviewer: no tool calls and no signal. Exiting loop.")
            break

        # ── Execute tool calls ─────────────────────────────────────────────
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]

            logger.info(f"Reviewer tool: {tool_name}")

            # ── Path injection ─────────────────────────────────────────────
            if tool_name in ("read_file", "write_file"):
                path = tool_args.get("path", "")
            if path:
                if path.startswith("/workspace"):
                    # Container path → map to actual working dir
                    relative = path[len("/workspace"):].lstrip("/")
                    tool_args["path"] = str(Path(working_dir) / relative)
                elif not Path(path).is_absolute():
                    tool_args["path"] = str(Path(working_dir) / path)
                    
            if tool_name == "shell_exec":
                tool_args["log_path"] = state.get("log_path", "")
                tool_args["iteration"] = iteration
            
            if tool_name == "write_file":
                content_val = tool_args.get("content", "")
                if isinstance(content_val, dict):
                    tool_args["content"] = json.dumps(content_val, indent=2)
            

            tool_fn = REVIEWER_TOOL_MAP.get(tool_name)
            if tool_fn is None:
                result = {"success": False, "message": f"Unknown tool: {tool_name}"}
            else:
                result = tool_fn.invoke(tool_args)

            messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call_id,
                )
            )

    return review_findings.strip(), item_doc.strip()


# ── Phase 2 — Verdict Call ────────────────────────────────────────────────────

def _get_verdict(
    llm,
    review_findings: str,
    state: GraphState,
) -> ReviewerVerdict:
    """
    Single structured LLM call to get the reviewer verdict.
    Uses with_structured_output — no manual parsing needed.
    """
    verdict_llm = llm.with_structured_output(ReviewerVerdict)

    prompt = REVIEWER_VERDICT_PROMPT.format(
        review_findings=review_findings or "No findings recorded.",
        plan_progress=format_plan_progress(state),
    )

    try:
        result: ReviewerVerdict = verdict_llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Return your verdict now."),
        ])
        logger.info(
            f"Reviewer verdict: {result.verdict} | "
            f"routing: {result.routing_decision} | "
            f"reason: {result.reason}"
        )
        return result

    except Exception as e:
        logger.error(f"Verdict call failed: {e}. Defaulting to tester.")
        return ReviewerVerdict(
            verdict="rejected",
            routing_decision="tester",
            reason=f"Verdict call failed: {e}",
            issues_found=[],
        )


# ── Final Doc ─────────────────────────────────────────────────────────────────

def _write_final_doc(state: GraphState, llm) -> str:
    """
    Called once when all items are approved.
    Writes complete project documentation.
    Returns the final doc string.
    """
    logger.info("Reviewer: writing final project documentation.")

    prompt = REVIEWER_FINAL_PROMPT.format(
        task_docs=format_task_docs(state.get("task_docs", [])),
        completed_plan=format_plan_for_prompt(state.get("plan", [])),
    )

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content="Write the final project documentation now."),
    ])

    final_doc = response.content or ""

    # Write to workspace
    working_dir = state.get("working_dir", "/workspace")
    doc_path = str(Path(working_dir) / "DOCUMENTATION.md")
    write_file.invoke({"path": doc_path, "content": final_doc})
    logger.info(f"Final documentation written to: {doc_path}")

    return final_doc


# ── Reviewer Node ─────────────────────────────────────────────────────────────

def reviewer_node(state: GraphState) -> GraphState:
    """
    Reviewer node.

    Phase 1: Mini loop reads files and writes per-item documentation.
    Phase 2: Single verdict call sets routing_decision.
    If last item and approved: writes final project documentation.
    """
    current_item = get_current_plan_item(state)

    if current_item is None:
        logger.error("Reviewer: no current item found. Routing to end.")
        return {**state, "routing_decision": "end"}

    logger.info(f"Reviewer: reviewing item [{current_item.id}] {current_item.title}")

    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.model_name,
    )
    llm_with_tools = llm.bind_tools(REVIEWER_TOOLS)

    # ── Phase 1 — Review Loop ──────────────────────────────────────────────
    review_findings, item_doc = _run_review_loop(
        state=state,
        llm_with_tools=llm_with_tools,
        current_item=current_item,
    )

    # Accumulate per-item docs
    updated_task_docs = list(state.get("task_docs", []))
    if item_doc:
        updated_task_docs.append(item_doc)

    # ── Phase 2 — Verdict ──────────────────────────────────────────────────
    verdict = _get_verdict(
        llm=llm,
        review_findings=review_findings,
        state=state,
    )

    # ── Routing decision ───────────────────────────────────────────────────
    final_doc = state.get("final_doc")
    current_index = state.get("current_item_index", 0)
    
    if verdict.verdict == "approved" and is_last_item(state):
        final_doc = _write_final_doc(state, llm)
        routing = "end"
        next_index = current_index

    elif verdict.verdict == "approved":
        routing = "next_item"
        next_index = current_index+1

    else:
        routing = "tester"
        next_index = current_index 

    logger.info(f"Reviewer: final routing → {routing}")

    return {
        **state,
        "review_output": review_findings,
        "task_docs": updated_task_docs,
        "final_doc": final_doc,
        "routing_decision": routing,
        "current_item_index": next_index,
    }