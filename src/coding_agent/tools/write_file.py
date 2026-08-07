# src/coding_agent/tools/write_file.py

import json
from pathlib import Path
from langchain_core.tools import tool

from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


@tool
def write_file(path: str, content: str) -> dict:
    """
    Creates a new file or fully overwrites an existing one.
    Use this when creating a file from scratch.
    For targeted edits to an existing file use edit_file instead.

    Args:
        path: File path relative to the working directory.
        content: Full content to write to the file.

    Returns:
        dict with keys: success (bool), path (str), message (str)
    """
    try:
        if isinstance(content, dict):
            content = json.dumps(content, indent=2)
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"File written: {path}")
        return {
            "success": True,
            "path": str(file_path),
            "message": f"File written successfully: {path}",
        }
    except OSError as e:
        logger.error(f"Failed to write file {path}: {e}")
        return {
            "success": False,
            "path": path,
            "message": f"Failed to write file: {e}",
        }