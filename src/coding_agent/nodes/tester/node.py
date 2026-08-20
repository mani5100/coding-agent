# src/coding_agent/nodes/tester/node.py

import json
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from coding_agent.graph.state import GraphState
from coding_agent.core.config import settings
from coding_agent.core.log_manager import get_logger
from coding_agent.nodes.planner.helpers import get_current_plan_item
from coding_agent.nodes.tester.prompts import TESTER_WRITE_PROMPT, TESTER_JUDGE_PROMPT
from coding_agent.nodes.tester.helpers import (
    JudgeResponse,
    detect_language,
    format_test_results,
    get_test_file_path,
    get_integration_test_path,
)
from coding_agent.tools.write_file import write_file
from coding_agent.tools.edit_file import edit_file
from coding_agent.tools.read_file import read_file
from coding_agent.tools.shell_exec import shell_exec
from coding_agent.tools.error_log import read_error_log

logger = get_logger(__name__)

MAX_TESTER_ITERATIONS = 100

# ── Tools ─────────────────────────────────────────────────────────────────────

TESTER_TOOLS = [read_file, write_file, edit_file, shell_exec, read_error_log]
TESTER_TOOL_MAP = {t.name: t for t in TESTER_TOOLS}


# ── Phase 1 — Write and Run Tests ─────────────────────────────────────────────

def _run_test_loop(
    state: GraphState,
    llm_with_tools,
    current_item,
    language: str,
) -> str:
    """
    Mini agent loop that writes and runs tests.
    Returns formatted test results string.
    Exits when LLM signals TESTS_WRITTEN or max iterations hit.
    """
    working_dir = state.get("working_dir", "/workspace")
    log_path = state.get("log_path", "")
    completed_items = state.get("completed_items", [])

    unit_test_path = get_test_file_path(current_item.id, language)
    integration_test_path = get_integration_test_path(language)

    system_prompt = TESTER_WRITE_PROMPT.format(
        item_id=current_item.id,
        item_title=current_item.title,
        item_description=current_item.description,
        acceptance_criteria=current_item.acceptance_criteria,
        completed_items="\n".join(
            f"- [{i.id}] {i.title}" for i in completed_items
        ) or "None yet",
        working_dir=working_dir,
        code_output=state.get("code_output") or "Not available",
        unit_test_path=unit_test_path,
        integration_test_path=integration_test_path,
    )

    messages = [HumanMessage(content=f"Write and run tests for: {current_item.title}")]
    last_stdout = ""
    last_stderr = ""
    last_exit_code = 1

    for iteration in range(1, MAX_TESTER_ITERATIONS + 1):
        logger.info(f"Tester loop iteration {iteration}/{MAX_TESTER_ITERATIONS}")

        response: AIMessage = llm_with_tools.invoke(
            [SystemMessage(content=system_prompt)] + messages
        )
        messages.append(response)

        content = response.content or ""
        logger.debug(f"Tester LLM response: {content[:200] or '[no content]'}")

        # ── Exit signal ────────────────────────────────────────────────────
        if "TESTS_WRITTEN" in content.upper():
            logger.info("Tester: TESTS_WRITTEN signal received.")
            break

        # ── No tool calls ──────────────────────────────────────────────────
        if not response.tool_calls:
            logger.warning("Tester: no tool calls and no signal. Exiting loop.")
            break

        # ── Execute tool calls ─────────────────────────────────────────────
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]

            logger.info(f"Tester tool: {tool_name}")

            # ── State injections ───────────────────────────────────────────
            if tool_name == "shell_exec":
                tool_args["log_path"] = log_path
                tool_args["iteration"] = iteration

            if tool_name == "read_error_log":
                tool_args["log_path"] = log_path

            if tool_name in ("write_file", "edit_file", "read_file"):
                path = tool_args.get("path", "")
                if path:
                    if path.startswith("/workspace"):
                        # Container path → map to actual working dir
                        relative = path[len("/workspace"):].lstrip("/")
                        tool_args["path"] = str(Path(working_dir) / relative)
                    elif not Path(path).is_absolute():
                        tool_args["path"] = str(Path(working_dir) / path)

            if tool_name == "write_file":
                content_val = tool_args.get("content", "")
                if isinstance(content_val, dict):
                    tool_args["content"] = json.dumps(content_val, indent=2)

            tool_fn = TESTER_TOOL_MAP.get(tool_name)
            
            if tool_fn is None:
                result = {
                    "success": False,
                    "message": f"Unknown tool: {tool_name}",
                }
            
            elif tool_name in ("write_file", "edit_file"):
                path = tool_args.get("path", "")
            
                if not _is_allowed_test_path(path, working_dir):
                    logger.warning(
                        f"Tester blocked from modifying non-test file: {path}"
                    )
            
                    result = {
                        "success": False,
                        "message": (
                            "TESTER_PERMISSION_DENIED: "
                            "The Tester may only create or modify test files. "
                            f"Production/source file modification is not allowed: {path}. "
                            "If application code needs to change, report the failure "
                            "so it can be routed back to the Coder."
                        ),
                    }
                else:
                    result = tool_fn.invoke(tool_args)
            
            else:
                result = tool_fn.invoke(tool_args)

            # ── Track last shell result for judge ──────────────────────────
            if tool_name == "shell_exec":
                last_stdout = result.get("stdout", "")
                last_stderr = result.get("stderr", "")
                last_exit_code = result.get("exit_code", 1)

            messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call_id,
                )
            )

    return format_test_results(last_stdout, last_stderr, last_exit_code)


# ── Phase 2 — Judge Results ───────────────────────────────────────────────────

def _judge_results(
    llm,
    test_results: str,
    current_item,
) -> JudgeResponse:
    """
    Single structured LLM call to judge test results.
    Uses with_structured_output so no manual parsing needed.
    """
    judge_llm = llm.with_structured_output(JudgeResponse)

    prompt = TESTER_JUDGE_PROMPT.format(
        test_results=test_results,
        item_id=current_item.id,
        acceptance_criteria=current_item.acceptance_criteria,
    )

    try:
        result: JudgeResponse = judge_llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Analyze the test results and return your verdict."),
        ])
        logger.info(
            f"Judge verdict: {result.verdict} | "
            f"routing: {result.routing_decision} | "
            f"severity: {result.severity}"
        )
        return result

    except Exception as e:
        logger.error(f"Judge call failed: {e}. Defaulting to coder routing.")
        return JudgeResponse(
            verdict="failed",
            routing_decision="coder",
            summary=f"Judge call failed: {e}",
            failed_tests=[],
            severity="minor",
        )


# ── Tester Node ───────────────────────────────────────────────────────────────

def tester_node(state: GraphState) -> GraphState:
    """
    Tester node.

    Phase 1: Mini agent loop writes and runs tests using existing tools.
    Phase 2: Single judge call sets routing_decision.
    """
    current_item = get_current_plan_item(state)

    if current_item is None:
        logger.error("Tester: no current plan item. Routing to end.")
        return {**state, "routing_decision": "end"}

    logger.info(f"Tester: testing item [{current_item.id}] {current_item.title}")

    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=settings.model_name,
    )
    llm_with_tools = llm.bind_tools(TESTER_TOOLS)

    working_dir = state.get("working_dir", "/workspace")
    language = detect_language(working_dir)
    logger.info(f"Tester: detected language={language}")

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    test_results = _run_test_loop(
        state=state,
        llm_with_tools=llm_with_tools,
        current_item=current_item,
        language=language,
    )

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    judge = _judge_results(
        llm=llm,
        test_results=test_results,
        current_item=current_item,
    )

    logger.info(f"Tester: routing to {judge.routing_decision}")

    return {
        **state,
        "test_results": f"{judge.summary}\n\n{test_results}",
        "routing_decision": judge.routing_decision,
    }
    
    
def _is_allowed_test_path(path: str, working_dir: str) -> bool:
    """
    Tester may only write/edit test files.

    Allowed examples:
      /workspace/tests/test_api.py
      /workspace/backend/tests/test_auth.py
      /workspace/frontend/src/__tests__/App.test.tsx
      /workspace/frontend/src/App.test.tsx
      /workspace/frontend/src/App.spec.tsx

    Production source files are rejected.
    """
    if not path:
        return False

    file_path = Path(path)

    # Map /workspace paths to actual working directory
    if path.startswith("/workspace"):
        relative = path[len("/workspace"):].lstrip("/")
        file_path = Path(working_dir) / relative
    elif not file_path.is_absolute():
        file_path = Path(working_dir) / file_path

    try:
        relative_path = file_path.resolve().relative_to(
            Path(working_dir).resolve()
        )
    except ValueError:
        return False

    parts = {part.lower() for part in relative_path.parts}
    filename = relative_path.name.lower()

    # Explicit test directories
    if "tests" in parts or "__tests__" in parts or "test" in parts:
        return True

    # Common test-file conventions
    if filename.startswith("test_"):
        return True

    if filename.endswith("_test.py"):
        return True

    if ".test." in filename:
        return True

    if ".spec." in filename:
        return True

    return False