# src/coding_agent/nodes/tester/helpers.py

from typing import Literal
from pydantic import BaseModel

from coding_agent.core.log_manager import get_logger
from coding_agent.tools.shell_exec import _sandbox

logger = get_logger(__name__)


# ── Judge Response Schema ─────────────────────────────────────────────────────

class JudgeResponse(BaseModel):
    """
    Structured output schema for the Tester judge call.
    Used with llm.with_structured_output(JudgeResponse).
    Literal types enforce valid values at the schema level.
    """
    verdict: Literal["passed", "failed"]
    routing_decision: Literal["reviewer", "coder", "planner"]
    summary: str
    failed_tests: list[str]
    severity: Literal["none", "minor", "major"]


# ── Test File Paths ───────────────────────────────────────────────────────────

def get_test_file_path(item_id: str, language: str) -> str:
    """
    Returns the unit test file path for the given item and language.

    Python     → /workspace/tests/test_{item_id}.py
    JavaScript → /workspace/tests/test_{item_id}.test.js
    """
    if language == "javascript":
        return f"/workspace/tests/test_{item_id}.test.js"
    return f"/workspace/tests/test_{item_id}.py"


def get_integration_test_path(language: str) -> str:
    """
    Returns the integration test file path for the given language.

    Python     → /workspace/tests/test_integration.py
    JavaScript → /workspace/tests/test_integration.test.js
    """
    if language == "javascript":
        return "/workspace/tests/test_integration.test.js"
    return "/workspace/tests/test_integration.py"


# ── Test Results Formatter ────────────────────────────────────────────────────

def format_test_results(stdout: str, stderr: str, exit_code: int) -> str:
    """
    Formats raw shell output from running tests into a clean
    structured string for injection into TESTER_JUDGE_PROMPT.
    """
    lines = []

    lines.append(f"Exit Code: {exit_code}")
    lines.append("")

    lines.append("STDOUT:")
    lines.append(stdout.strip() if stdout.strip() else "(empty)")
    lines.append("")

    lines.append("STDERR:")
    lines.append(stderr.strip() if stderr.strip() else "(empty)")

    return "\n".join(lines)


# ── Language Detection ────────────────────────────────────────────────────────

def detect_language(working_dir: str) -> str:
    """
    Detects the primary language of the project by inspecting
    files inside the container sandbox.

    Returns "javascript" if package.json found.
    Returns "python" if any .py file found.
    Falls back to "python" if neither found.
    """
    if _sandbox is None:
        logger.warning("detect_language: sandbox not initialized. Defaulting to python.")
        return "python"

    # Check for JavaScript/Node project
    exit_code, _, _ = _sandbox.exec(
        f"test -f {working_dir}/package.json || "
        f"test -f {working_dir}/frontend/package.json"
    )
    if exit_code == 0:
        logger.debug("detect_language: detected javascript")
        return "javascript"

    # Check for Python project
    exit_code, stdout, _ = _sandbox.exec(
        f"find {working_dir} -maxdepth 3 -name '*.py' | head -1"
    )
    if exit_code == 0 and stdout.strip():
        logger.debug("detect_language: detected python")
        return "python"

    logger.warning("detect_language: could not detect. Defaulting to python.")
    return "python"