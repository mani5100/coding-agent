# src/coding_agent/phases/act.py

from collections import Counter
from pathlib import Path
import json

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from coding_agent.core.config import settings
from coding_agent.core.state import AgentState, AgentStatus
from coding_agent.core.prompts import ACT_SYSTEM_PROMPT
from coding_agent.core.log_manager import get_logger
from coding_agent.tools.error_log import format_logs_for_llm
from coding_agent.tools.write_file import write_file
from coding_agent.tools.edit_file import edit_file
from coding_agent.tools.read_file import read_file
from coding_agent.tools.shell_exec import shell_exec
from coding_agent.tools.error_log import read_error_log
from coding_agent.tools.test_frontend import test_frontend

logger = get_logger(__name__)

# ── LLM + Tools Setup ─────────────────────────────────────────────────────────
TOOLS = [write_file, edit_file, read_file, shell_exec, read_error_log, test_frontend]
TOOL_MAP = {t.name: t for t in TOOLS}

REPEAT_THRESHOLD = 3  # same failing command N times = stuck

llm = ChatOllama(
    base_url=settings.ollama_base_url,
    model=settings.model_name,
)
llm_with_tools = llm.bind_tools(TOOLS)


# ── Act Phase ─────────────────────────────────────────────────────────────────

def act(state: AgentState) -> AgentState:
    """
    Phase 2 — Act.
    Runs the tool-calling loop until:
      - LLM signals DONE
      - max_iterations is reached
      - Same failing command repeats REPEAT_THRESHOLD times (stuck detection)
    """
    logger.info("=== ACT PHASE ===")

    messages = [HumanMessage(content=state.task)]

    # ── Stuck detection: tracks (command, exit_code) for failing commands only
    recent_failures: list[tuple[str, int]] = []

    while state.iteration < state.max_iterations:
        state.iteration += 1
        logger.info(f"--- Iteration {state.iteration} / {state.max_iterations} ---")

        # ── Build system prompt with current state ─────────────────────
        system_prompt = ACT_SYSTEM_PROMPT.format(
            task=state.task,
            iteration=state.iteration,
            max_iterations=state.max_iterations,
            files_touched=state.files_touched or "None",
            working_dir=settings.container_workdir,
            logs=format_logs_for_llm(state.log_path),
        )

        # ── Call LLM ───────────────────────────────────────────────────
        response: AIMessage = llm_with_tools.invoke(
            [SystemMessage(content=system_prompt)] + messages
        )

        messages.append(response)
        logger.debug(f"LLM response: {response.content[:200] if response.content else '[no content]'}")

        # ── Check for DONE signal ──────────────────────────────────────
        if response.content and "DONE" in response.content.upper():
            logger.info("LLM signaled DONE.")
            state.status = AgentStatus.DONE
            state.final_output = response.content
            break

        # ── No tool calls — LLM is stuck or confused ───────────────────
        if not response.tool_calls:
            logger.warning("LLM returned no tool calls and no DONE signal.")
            break

        # ── Execute tool calls ─────────────────────────────────────────
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]

            logger.info(f"Tool call: {tool_name} | args={tool_args}")

            tool_fn = TOOL_MAP.get(tool_name)
            if tool_fn is None:
                result = {"success": False, "message": f"Unknown tool: {tool_name}"}
                logger.error(f"Unknown tool requested: {tool_name}")
            else:
                # ── Inject state args the LLM does not supply ──────────
                if tool_name == "shell_exec":
                    tool_args["log_path"] = state.log_path
                    tool_args["iteration"] = state.iteration

                if tool_name == "read_error_log":
                    tool_args["log_path"] = state.log_path

                if tool_name in ("write_file", "edit_file", "read_file"):
                    path = tool_args.get("path", "")
                    if path:
                        if path.startswith("/workspace"):
                            # Container path → map to actual working dir
                            relative = path[len("/workspace"):].lstrip("/")
                            tool_args["path"] = str(Path(state.working_dir) / relative)
                        elif not Path(path).is_absolute():
                            tool_args["path"] = str(Path(state.working_dir) / path)

                # ── Guard: dict content for JSON files ─────────────────
                if tool_name == "write_file":
                    content = tool_args.get("content", "")
                    if isinstance(content, dict):
                        tool_args["content"] = json.dumps(content, indent=2)
                        logger.debug("Converted dict content to JSON string for write_file")

                # ── Guard: block Coder from writing/editing test files ───
                # Testing is the Tester node's job. If the Coder writes tests
                # itself, the Tester's judge call has nothing independent
                # left to verify against.
                if tool_name in ("write_file", "edit_file") and _is_test_path(
                    tool_args.get("path", ""), state.working_dir
                ):
                    logger.warning(
                        f"Blocked Coder from touching test file: {tool_args.get('path', '')}"
                    )
                    result = {
                        "success": False,
                        "path": tool_args.get("path", ""),
                        "message": (
                            "CODER_PERMISSION_DENIED: You may not create or edit test files. "
                            "Testing is handled separately by the Tester agent. Focus only on "
                            "the production/application code needed to satisfy this task."
                        ),
                    }

                # ── Guard: block write_file on files that already exist ─
                # Full-file rewrites from the model are the source of the
                # whitespace/indentation corruption seen in practice. Force
                # existing files through edit_file's targeted diffs instead.
                elif tool_name == "write_file":
                    target_path = Path(tool_args.get("path", ""))
                    if target_path.exists():
                        logger.warning(
                            f"Blocked write_file on existing file: {target_path}"
                        )
                        result = {
                            "success": False,
                            "path": str(target_path),
                            "message": (
                                f"'{target_path}' already exists. write_file cannot be used "
                                "on existing files (it causes full-file rewrites that risk "
                                "corrupting content). Use edit_file with a targeted old_string/"
                                "new_string change instead."
                            ),
                        }
                    else:
                        result = tool_fn.invoke(tool_args)
                else:
                    result = tool_fn.invoke(tool_args)

            # ── Track files touched ────────────────────────────────────
            if tool_name in ("write_file", "edit_file") and result.get("success"):
                path = tool_args.get("path", "")
                if path and path not in state.files_touched:
                    state.files_touched.append(path)

            state.last_tool_used = tool_name
            state.last_tool_result = result

            # ── Stuck detection: only track failing shell commands ──────
            if tool_name == "shell_exec":
                exit_code = result.get("exit_code", 0)
                cmd = tool_args.get("command", "")

                if exit_code != 0:
                    recent_failures.append((cmd, exit_code))

                    # Keep window to last 10 failures
                    if len(recent_failures) > 10:
                        recent_failures.pop(0)

                    counts = Counter(recent_failures)
                    most_common, most_common_count = counts.most_common(1)[0]

                    if most_common_count >= REPEAT_THRESHOLD:
                        logger.warning(
                            f"Stuck detected: command failed {most_common_count} times "
                            f"with exit_code={most_common[1]}: {most_common[0]!r}"
                        )
                        state.status = AgentStatus.FAILED
                        state.final_output = (
                            f"Agent stuck: command '{most_common[0]}' failed "
                            f"{most_common_count} times with exit_code={most_common[1]}"
                        )
                        return state

            # ── Add tool result to message history ─────────────────────
            messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call_id,
                )
            )

    # ── Max iterations hit ─────────────────────────────────────────────
    if state.iteration >= state.max_iterations and state.status == AgentStatus.RUNNING:
        logger.warning("Max iterations reached without DONE signal.")
        state.status = AgentStatus.PARTIAL

    return state



def _is_test_path(path: str, working_dir: str) -> bool:
    """
    Returns True if the given path looks like a test file/location.
    Mirrors tester/node.py's _is_allowed_test_path, but used here to
    BLOCK the Coder from touching test files — testing is the Tester's job.
    """
    if not path:
        return False

    file_path = Path(path)

    if path.startswith("/workspace"):
        relative = path[len("/workspace"):].lstrip("/")
        file_path = Path(working_dir) / relative
    elif not file_path.is_absolute():
        file_path = Path(working_dir) / file_path

    try:
        relative_path = file_path.resolve().relative_to(Path(working_dir).resolve())
    except ValueError:
        return False

    parts = {part.lower() for part in relative_path.parts}
    filename = relative_path.name.lower()

    if "tests" in parts or "__tests__" in parts or "test" in parts:
        return True
    if filename.startswith("test_"):
        return True
    if filename.endswith("_test.py"):
        return True
    if ".test." in filename:
        return True
    if ".spec." in filename:
        return True

    return False