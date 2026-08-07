# src/coding_agent/core/config.py

import tempfile
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Ollama ────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    model_name: str = "qwen3-coder-next:latest"

    # ── Agent Loop ────────────────────────────────────────────────────
    max_iterations: int = 10
    max_verify_attempts: int = 3

    # ── Sandbox (Docker) ──────────────────────────────────────────────
    docker_image: str = "nikolaik/python-nodejs:python3.11-nodejs20"
    container_workdir: str = "/workspace"
    shell_timeout: int = 30

    # ── Logging ───────────────────────────────────────────────────────
    log_filename: str = "run_log.json"
    max_log_entries: int = 20
    stdout_tail_lines: int = 50
    error_fingerprint_length: int = 300

    # ── Paths ─────────────────────────────────────────────────────────
    base_working_dir: Path = Path(tempfile.gettempdir()) / "coding_agent_workspace"


settings = Settings()