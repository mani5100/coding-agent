# src/coding_agent/tools/read_file.py

from pathlib import Path
from langchain_core.tools import tool

from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


@tool
def read_file(path: str) -> dict:
    """
    Reads and returns the content of a file.
    Use this before editing a file to verify exact content.
    Also use this to read JSON files, error outputs, or any text based file.

    Args:
        path: File path relative to the working directory.

    Returns:
        dict with keys: success (bool), path (str), content (str), message (str)
    """
    try:
        file_path = Path(path)

        if not file_path.exists():
            logger.error(f"File not found: {path}")
            return {
                "success": False,
                "path": path,
                "content": "",
                "message": f"File not found: {path}",
            }

        if not file_path.is_file():
            logger.error(f"Path is not a file: {path}")
            return {
                "success": False,
                "path": path,
                "content": "",
                "message": f"Path is not a file: {path}",
            }

        content = file_path.read_text(encoding="utf-8")
        logger.info(f"File read: {path} ({len(content)} chars)")
        return {
            "success": True,
            "path": path,
            "content": content,
            "message": f"File read successfully: {path}",
        }

    except OSError as e:
        logger.error(f"Failed to read file {path}: {e}")
        return {
            "success": False,
            "path": path,
            "content": "",
            "message": f"Failed to read file: {e}",
        }