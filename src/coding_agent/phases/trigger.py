# src/coding_agent/phases/trigger.py

import uuid
from pathlib import Path

from coding_agent.core.config import settings
from coding_agent.core.state import AgentState
from coding_agent.core.log_manager import get_logger
from coding_agent.sandbox.docker_sandbox import DockerSandbox
from coding_agent.tools.shell_exec import set_sandbox

logger = get_logger(__name__)


def trigger(task: str) -> tuple[AgentState, DockerSandbox]:
    """
    Phase 1 — Trigger.
    Receives the user task, sets up the workspace,
    starts the sandbox, and returns initialized state.

    Args:
        task: Raw user prompt.

    Returns:
        Tuple of (AgentState, DockerSandbox)
    """
    logger.info("=== TRIGGER PHASE ===")
    logger.info(f"Task received: {task}")

    # ── Working Directory ──────────────────────────────────────────────
    session_id = uuid.uuid4().hex[:8]
    working_dir = settings.base_working_dir / session_id
    working_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(working_dir / settings.log_filename)

    logger.info(f"Session ID  : {session_id}")
    logger.info(f"Working dir : {working_dir}")
    logger.info(f"Log path    : {log_path}")

    # ── Initialize State ──────────────────────────────────────────────
    state = AgentState(
        task=task,
        working_dir=str(working_dir),
        log_path=log_path,
        max_iterations=settings.max_iterations,
    )

    # ── Start Sandbox ─────────────────────────────────────────────────
    sandbox = DockerSandbox(working_dir=str(working_dir))
    sandbox.start()

    # ── Inject Sandbox into shell_exec tool ───────────────────────────
    set_sandbox(sandbox)

    logger.info("Trigger phase complete. Handing off to Act.")
    return state, sandbox