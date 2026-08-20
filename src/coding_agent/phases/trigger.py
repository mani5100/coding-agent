# src/coding_agent/phases/trigger.py

import uuid
from pathlib import Path

from coding_agent.core.config import settings
from coding_agent.core.state import AgentState
from coding_agent.core.log_manager import get_logger
from coding_agent.sandbox.docker_sandbox import DockerSandbox
from coding_agent.tools.shell_exec import set_sandbox

logger = get_logger(__name__)


def trigger(task: str, working_dir: str | None = None, sandbox=None) -> tuple[AgentState, DockerSandbox]:
    """
    Phase 1 — Trigger.
    Sets up workspace and sandbox, returns initialized AgentState.

    Args:
        task:        Raw task string.
        working_dir: Optional existing directory to reuse.
                     If None, a new session directory is created.
                     Pass this when running inside a graph so all
                     plan items share the same sandbox workspace.
    """
    logger.info("=== TRIGGER PHASE ===")
    logger.info(f"Task received: {task[:100]}...")

    # ── Working Directory ──────────────────────────────────────────────────
    if working_dir:
        session_id = Path(working_dir).name
        work_path = Path(working_dir)
        work_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Reusing working dir : {work_path}")
    else:
        session_id = uuid.uuid4().hex[:8]
        work_path = settings.base_working_dir / session_id
        work_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Session ID  : {session_id}")
        logger.info(f"Working dir : {work_path}")

    log_path = str(work_path / settings.log_filename)
    logger.info(f"Log path    : {log_path}")

    # ── Initialize State ───────────────────────────────────────────────────
    state = AgentState(
        task=task,
        working_dir=str(work_path),
        log_path=log_path,
        max_iterations=settings.max_iterations,
    )

    if sandbox is not None:
        logger.info("Reusing existing sandbox from graph.")
        set_sandbox(sandbox)
        return state, sandbox

    sandbox = DockerSandbox(working_dir=str(work_path))
    sandbox.start()
    set_sandbox(sandbox)

    logger.info("Trigger phase complete. Handing off to Act.")
    return state, sandbox