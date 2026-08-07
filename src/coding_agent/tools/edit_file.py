# src/coding_agent/tools/edit_file.py

from pathlib import Path
from langchain_core.tools import tool

from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


@tool
def edit_file(path: str, old_str: str, new_str: str) -> dict:
    """
    Replaces a specific block of text in an existing file.
    Use this for targeted edits instead of rewriting the whole file.
    Fails loudly if old_str is not found or matches more than once.

    Args:
        path: File path relative to the working directory.
        old_str: The exact text block to find and replace.
        new_str: The text to replace it with.

    Returns:
        dict with keys: success (bool), path (str), message (str)
    """
    try:
        file_path = Path(path)

        if not file_path.exists():
            logger.error(f"File not found: {path}")
            return {
                "success": False,
                "path": path,
                "message": f"File not found: {path}",
            }

        content = file_path.read_text(encoding="utf-8")
        occurrences = content.count(old_str)

        if occurrences == 0:
            logger.error(f"old_str not found in {path}")
            return {
                "success": False,
                "path": path,
                "message": "old_str not found in file. Read the file first to verify the exact content.",
            }

        if occurrences > 1:
            logger.error(f"old_str found {occurrences} times in {path}, must be unique")
            return {
                "success": False,
                "path": path,
                "message": f"old_str matched {occurrences} times. Make old_str more specific so it matches exactly once.",
            }

        updated = content.replace(old_str, new_str, 1)
        file_path.write_text(updated, encoding="utf-8")

        logger.info(f"File edited: {path}")
        return {
            "success": True,
            "path": path,
            "message": f"File edited successfully: {path}",
        }

    except OSError as e:
        logger.error(f"Failed to edit file {path}: {e}")
        return {
            "success": False,
            "path": path,
            "message": f"Failed to edit file: {e}",
        }