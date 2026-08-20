# src/coding_agent/tools/read_file.py

from pathlib import Path
from langchain_core.tools import tool

from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)

BINARY_EXTENSIONS = {
    ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".7z",
    ".exe", ".dll", ".so", ".pyc",
}


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

        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            logger.warning(f"Refused to read binary file: {path}")
            return {
                "success": False,
                "path": path,
                "content": "",
                "message": f"Cannot read binary file as text: {path}",
            }

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            logger.warning(f"File is not valid UTF-8, refusing to read: {path} ({e})")
            return {
                "success": False,
                "path": path,
                "content": "",
                "message": f"Cannot read file: not valid UTF-8 text (likely binary): {path}",
            }

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