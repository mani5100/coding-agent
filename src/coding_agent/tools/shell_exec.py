# src/coding_agent/tools/shell_exec.py

from langchain_core.tools import tool

from coding_agent.sandbox.docker_sandbox import DockerSandbox
from coding_agent.core.log_manager import get_logger
from coding_agent.tools.error_log import write_log_entry

logger = get_logger(__name__)

_sandbox: DockerSandbox | None = None


def set_sandbox(sandbox: DockerSandbox) -> None:
    """Called once by Trigger phase to inject the active sandbox."""
    global _sandbox
    _sandbox = sandbox


@tool
def shell_exec(command: str, log_path: str, iteration: int) -> dict:
    """
    Executes a shell command inside the Docker sandbox.
    Runs in /workspace inside the Linux sandbox — never a host path. Each call is a fresh
    shell: `cd` from a previous call does not carry over. Use absolute paths or chain
    commands with && in one call.
    Results are automatically written to the run log.
    Use this to run scripts, install packages, or execute any shell command.

    Args:
        command: Shell command to execute.
        log_path: Path to run_log.json for storing the result.
        iteration: Current agent iteration number.

    Returns:
        dict with keys: success (bool), exit_code (int), stdout (str), stderr (str), message (str)
    """
    if _sandbox is None:
        logger.error("Sandbox is not initialized. Call set_sandbox() first.")
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "message": "Sandbox not initialized.",
        }

    logger.info(f"[iter={iteration}] Executing: {command!r}")
    exit_code, stdout, stderr = _sandbox.exec(command)

    write_log_entry(
        log_path=log_path,
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        iteration=iteration,
    )

    success = exit_code == 0
    return {
        "success": success,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "message": "Command succeeded." if success else f"Command failed with exit code {exit_code}.",
    }