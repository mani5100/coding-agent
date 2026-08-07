import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import tool

from coding_agent.core.config import settings
from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


# ── Helpers (called internally, not by agent) ─────────────────────────────────

def _tail(text: str, lines: int) -> str:
    all_lines = text.splitlines()
    return "\n".join(all_lines[-lines:])


def write_log_entry(
    log_path: str,
    command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    iteration: int,
) -> None:
    """
    Called internally by shell_exec after every command.
    Not exposed to the agent as a tool.
    """
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not parse existing log file. Starting fresh.")
            entries = []

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iteration": iteration,
        "command": command,
        "exit_code": exit_code,
        "stdout": _tail(stdout, settings.stdout_tail_lines) if exit_code == 0 else stdout,
        "stderr": stderr if exit_code != 0 else "",
    }

    entries.append(entry)

    try:
        path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        if exit_code == 0:
            logger.info(f"[iter={iteration}] Command succeeded: {command}")
        else:
            logger.error(f"[iter={iteration}] Command failed (exit={exit_code}): {command}")
            logger.error(f"stderr: {stderr[:300]}")
    except OSError as e:
        logger.error(f"Failed to write log entry: {e}")


def get_error_fingerprint(stderr: str) -> Optional[str]:
    """
    Called internally by Verify phase for change detection.
    Not exposed to the agent as a tool.
    """
    cleaned = stderr.strip()
    if not cleaned:
        return None
    return cleaned[:settings.error_fingerprint_length]


def format_logs_for_llm(log_path: str, errors_only: bool = True) -> str:
    """
    Called internally by Act phase to embed recent log entries into the system prompt.
    Not exposed to the agent as a tool.
    """
    path = Path(log_path)
    if not path.exists():
        return "No logs yet."

    try:
        entries: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read log file: {e}")
        return "No logs yet."

    if errors_only:
        entries = [e for e in entries if e.get("exit_code", 0) != 0]

    entries = entries[-settings.max_log_entries:]
    if not entries:
        return "No logs yet."

    lines = []
    for e in entries:
        lines.append(f"[iter={e['iteration']} | exit={e['exit_code']}]")
        lines.append(f"  CMD : {e['command']}")
        if e.get("stdout"):
            lines.append(f"  OUT : {e['stdout'][:500]}")
        if e.get("stderr"):
            lines.append(f"  ERR : {e['stderr']}")
        lines.append("")

    return "\n".join(lines).strip()


# ── Tool (called by agent) ────────────────────────────────────────────────────

@tool
def read_error_log(log_path: str, errors_only: bool = False) -> dict:
    """
    Reads the shell execution log file.
    Use this to inspect what commands have run and what errors occurred.
    Always call this before retrying a failed command.

    Args:
        log_path: Path to run_log.json.
        errors_only: If True, returns only entries where exit_code != 0.

    Returns:
        dict with keys: success (bool), entries (list), formatted (str), message (str)
    """
    path = Path(log_path)

    if not path.exists():
        logger.debug("Log file does not exist yet.")
        return {
            "success": False,
            "entries": [],
            "formatted": "No logs yet.",
            "message": "Log file not found.",
        }

    try:
        entries: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read log file: {e}")
        return {
            "success": False,
            "entries": [],
            "formatted": "",
            "message": f"Failed to read log file: {e}",
        }

    if errors_only:
        entries = [e for e in entries if e.get("exit_code", 0) != 0]

    entries = entries[-settings.max_log_entries:]

    # Format for readability
    lines = []
    for e in entries:
        lines.append(f"[iter={e['iteration']} | exit={e['exit_code']}]")
        lines.append(f"  CMD : {e['command']}")
        if e.get("stdout"):
            lines.append(f"  OUT : {e['stdout'][:500]}")
        if e.get("stderr"):
            lines.append(f"  ERR : {e['stderr']}")
        lines.append("")

    formatted = "\n".join(lines).strip() or "No matching entries."

    return {
        "success": True,
        "entries": entries,
        "formatted": formatted,
        "message": f"Retrieved {len(entries)} log entries.",
    }