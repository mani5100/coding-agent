# src/coding_agent/phases/act.py

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

from pathlib import Path

logger = get_logger(__name__)

# ── LLM + Tools Setup ─────────────────────────────────────────────────────────

TOOLS = [write_file, edit_file, read_file, shell_exec, read_error_log]
TOOL_MAP = {t.name: t for t in TOOLS}

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
      - LLM responds with DONE
      - max_iterations is reached
    """
    logger.info("=== ACT PHASE ===")

    messages = [HumanMessage(content=state.task)]

    while state.iteration < state.max_iterations:
        state.iteration += 1
        logger.info(f"--- Iteration {state.iteration} / {state.max_iterations} ---")

        # ── Build system prompt with current state ─────────────────────
        system_prompt = ACT_SYSTEM_PROMPT.format(
            task=state.task,
            iteration=state.iteration,
            max_iterations=state.max_iterations,
            files_touched=state.files_touched or "None",
            working_dir=state.working_dir,
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
                # Inject state args the LLM does not supply
                # ── Inject state args the LLM does not supply ─────────────────────
                if tool_name == "shell_exec":
                    tool_args["log_path"] = state.log_path
                    tool_args["iteration"] = state.iteration

                if tool_name == "read_error_log":
                    tool_args["log_path"] = state.log_path

                # ADD THIS — resolve relative file paths to working_dir
                if tool_name in ("write_file", "edit_file", "read_file"):
                    path = tool_args.get("path", "")
                    if path and not Path(path).is_absolute():
                        tool_args["path"] = str(Path(state.working_dir) / path)
                        
                if tool_name == "write_file":
                    content = tool_args.get("content", "")
                    if isinstance(content, dict):
                        tool_args["content"] = json.dumps(content, indent=2)
                        logger.debug("Converted dict content to JSON string for write_file")

                result = tool_fn.invoke(tool_args)

            # Track files touched
            if tool_name in ("write_file", "edit_file") and result.get("success"):
                path = tool_args.get("path", "")
                if path and path not in state.files_touched:
                    state.files_touched.append(path)

            state.last_tool_used = tool_name
            state.last_tool_result = result

            # Add tool result to message history
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