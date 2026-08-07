# src/coding_agent/core/state.py

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class AgentStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class AgentState:
    # ── Task ──────────────────────────────────────────────────────────
    task: str

    # ── Sandbox / File System ─────────────────────────────────────────
    working_dir: str        # host path mounted into the container
    log_path: str           # full path to run_log.json

    # ── Loop Control ──────────────────────────────────────────────────
    iteration: int = 0
    max_iterations: int = 10

    # ── Status ────────────────────────────────────────────────────────
    status: AgentStatus = AgentStatus.RUNNING

    # ── Tool Tracking ─────────────────────────────────────────────────
    files_touched: list[str] = field(default_factory=list)
    last_tool_used: Optional[str] = None
    last_tool_result: Optional[dict] = None

    # ── Error Fingerprinting ──────────────────────────────────────────
    last_error_fingerprint: Optional[str] = None
    verify_attempts: int = 0

    # ── Final Output ──────────────────────────────────────────────────
    final_output: Optional[str] = None