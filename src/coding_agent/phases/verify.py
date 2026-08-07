# src/coding_agent/phases/verify.py

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from coding_agent.core.config import settings
from coding_agent.core.state import AgentState, AgentStatus
from coding_agent.core.prompts import VERIFY_SYSTEM_PROMPT
from coding_agent.core.log_manager import get_logger
from coding_agent.tools.error_log import read_error_log, get_error_fingerprint

logger = get_logger(__name__)

llm = ChatOllama(
    base_url=settings.ollama_base_url,
    model=settings.model_name,
)


def _parse_verdict(response_text: str) -> tuple[str, str]:
    """
    Parses LLM verdict response.
    Returns (verdict, reason).
    """
    verdict = "FAILED"
    reason = "Could not parse verdict."

    for line in response_text.splitlines():
        line = line.strip()
        if line.startswith("VERDICT:"):
            verdict = line.replace("VERDICT:", "").strip().upper()
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()

    return verdict, reason


def _get_latest_error(state: AgentState) -> str:
    """Returns stderr of the most recent failed log entry."""
    result = read_error_log.invoke({
        "log_path": state.log_path,
        "errors_only": True,
    })
    entries = result.get("entries", [])
    if not entries:
        return ""
    return entries[-1].get("stderr", "")


def verify(state: AgentState, act_fn) -> AgentState:
    """
    Phase 3 — Verify.
    Reviews agent output and re-enters Act if errors are changing.
    Stops if:
      - Verdict is SUCCESS
      - Error fingerprint is unchanged (stuck)
      - max_verify_attempts is reached
    """
    logger.info("=== VERIFY PHASE ===")

    while True:
        # ── Build verify prompt ────────────────────────────────────────
        log_result = read_error_log.invoke({
            "log_path": state.log_path,
            "errors_only": False,
        })

        system_prompt = VERIFY_SYSTEM_PROMPT.format(
            task=state.task,
            files_touched=state.files_touched or "None",
            logs=log_result.get("formatted", "No logs available."),
        )

        # ── Call LLM for verdict ───────────────────────────────────────
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="Verify the task completion."),
        ])

        verdict, reason = _parse_verdict(response.content)
        logger.info(f"Verdict: {verdict} | Reason: {reason}")

        # ── SUCCESS — we are done ──────────────────────────────────────
        if verdict == "SUCCESS":
            state.status = AgentStatus.DONE
            state.final_output = reason
            logger.info("Task verified as complete.")
            break

        # ── FAILED or PARTIAL — check if we should re-enter Act ────────
        latest_stderr = _get_latest_error(state)
        current_fingerprint = get_error_fingerprint(latest_stderr)

        logger.debug(f"Current fingerprint : {current_fingerprint}")
        logger.debug(f"Last fingerprint    : {state.last_error_fingerprint}")

        # Stuck — same error repeating
        if current_fingerprint is None and state.last_error_fingerprint is None:
            logger.warning("No error fingerprint available. Cannot determine progress. Stopping.")
            state.status = AgentStatus.FAILED
            state.final_output = reason
            break
        
        # Same error repeating — agent is stuck
        if current_fingerprint and current_fingerprint == state.last_error_fingerprint:
            logger.warning("Error fingerprint unchanged. Agent is stuck. Stopping.")
            state.status = AgentStatus.FAILED
            state.final_output = reason
            break
        # Progress detected — re-enter Act
        state.last_error_fingerprint = current_fingerprint
        state.verify_attempts += 1
        logger.info(f"Error is changing. Re-entering Act (attempt {state.verify_attempts}/{settings.max_verify_attempts})")
        state = act_fn(state)

    return state