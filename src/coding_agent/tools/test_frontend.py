# src/coding_agent/tools/test_frontend.py

from langchain_core.tools import tool
from coding_agent.tools.shell_exec import _sandbox
from coding_agent.core.log_manager import get_logger

logger = get_logger(__name__)


# ── Known runtime patterns that build tools won't catch ───────────────────────

REACT_BAD_PATTERNS = [
    (
        "ReactDOM.render(",
        "ReactDOM.render is not a function in React 18. Use ReactDOM.createRoot instead:\n"
        "ReactDOM.createRoot(document.getElementById('root')).render(<App />)"
    ),
    (
        "componentWillMount",
        "componentWillMount is deprecated. Use componentDidMount instead."
    ),
    (
        "componentWillReceiveProps",
        "componentWillReceiveProps is deprecated. Use getDerivedStateFromProps instead."
    ),
    (
        "componentWillUpdate",
        "componentWillUpdate is deprecated. Use getSnapshotBeforeUpdate instead."
    ),
]


# ── Framework Detection ────────────────────────────────────────────────────────

def _detect_frontend_type(frontend_dir: str) -> str:
    """
    Detects frontend framework by inspecting files.
    Returns: 'vite' | 'react_cra' | 'vue' | 'flask' | 'django' | 'html' | 'unknown'
    """
    checks = [
        (f"test -f {frontend_dir}/vite.config.js || test -f {frontend_dir}/vite.config.ts", "vite"),
        (f"test -f {frontend_dir}/package.json && grep -q 'react-scripts' {frontend_dir}/package.json", "react_cra"),
        (f"test -f {frontend_dir}/vue.config.js", "vue"),
        (f"test -f {frontend_dir}/app.py && grep -qi 'flask' {frontend_dir}/app.py", "flask"),
        (f"test -f {frontend_dir}/manage.py", "django"),
        (f"test -f {frontend_dir}/index.html", "html"),
    ]

    for cmd, framework in checks:
        exit_code, stdout, _ = _sandbox.exec(cmd)
        if exit_code == 0:
            logger.debug(f"Detected framework: {framework}")
            return framework

    return "unknown"


# ── Framework-specific test functions ─────────────────────────────────────────

def _test_vite(frontend_dir: str) -> dict:
    """Test Vite/React/Vue via build check + runtime pattern grep."""

    # Step 1 — node_modules
    exit_code, stdout, _ = _sandbox.exec(
        f"test -d {frontend_dir}/node_modules && echo EXISTS || echo MISSING"
    )
    if "MISSING" in stdout:
        return {
            "success": False,
            "errors": "node_modules not found.",
            "warnings": "",
            "message": f"Run npm install in {frontend_dir} first.",
        }

    # Step 2 — Build check
    exit_code, stdout, stderr = _sandbox.exec(
        f"cd {frontend_dir} && npm run build 2>&1"
    )
    output = stdout + stderr
    if exit_code != 0:
        error_lines = [
            line for line in output.splitlines()
            if any(kw in line.lower() for kw in [
                "error", "failed", "cannot find",
                "is not defined", "unexpected token"
            ])
        ]
        return {
            "success": False,
            "errors": "\n".join(error_lines) or output[-1000:],
            "warnings": "",
            "message": "Build failed. Fix errors before starting dev server.",
        }

    # Step 3 — Runtime pattern checks
    errors = []
    for pattern, message in REACT_BAD_PATTERNS:
        exit_code, stdout, _ = _sandbox.exec(
            f"grep -rn '{pattern}' {frontend_dir}/src/ 2>/dev/null"
        )
        if exit_code == 0 and stdout.strip():
            errors.append(f"{message}\nFound at: {stdout.strip()}")

    if errors:
        return {
            "success": False,
            "errors": "\n\n".join(errors),
            "warnings": "",
            "message": "Build passed but runtime errors detected. Fix before starting dev server.",
        }

    return {
        "success": True,
        "errors": "",
        "warnings": "",
        "message": "Build passed and no runtime issues found. Safe to start dev server.",
    }


def _test_flask(frontend_dir: str) -> dict:
    """Test Flask app via Python syntax check."""

    exit_code, stdout, _ = _sandbox.exec(
        f"find {frontend_dir} -maxdepth 2 -name '*.py' | head -10"
    )
    py_files = [f for f in stdout.strip().splitlines() if f]

    if not py_files:
        return {
            "success": False,
            "errors": "No Python files found.",
            "warnings": "",
            "message": f"No .py files found in {frontend_dir}.",
        }

    errors = []
    for py_file in py_files:
        exit_code, stdout, stderr = _sandbox.exec(
            f"python -m py_compile {py_file} 2>&1"
        )
        if exit_code != 0:
            errors.append(f"{py_file}:\n{stderr}")

    if errors:
        return {
            "success": False,
            "errors": "\n".join(errors),
            "warnings": "",
            "message": "Syntax errors found in Flask files.",
        }

    # Check templates exist if render_template is used
    warnings = []
    exit_code, stdout, _ = _sandbox.exec(
        f"grep -r 'render_template' {frontend_dir} 2>/dev/null"
    )
    if exit_code == 0 and stdout.strip():
        exit_code2, _, _ = _sandbox.exec(
            f"test -d {frontend_dir}/templates"
        )
        if exit_code2 != 0:
            warnings.append("render_template used but no templates/ directory found.")

    return {
        "success": True,
        "errors": "",
        "warnings": "\n".join(warnings),
        "message": "Flask syntax valid. Safe to start the server.",
    }


def _test_django(frontend_dir: str) -> dict:
    """Test Django app via manage.py check."""

    exit_code, stdout, stderr = _sandbox.exec(
        f"cd {frontend_dir} && python manage.py check 2>&1"
    )
    output = stdout + stderr
    has_error = exit_code != 0

    return {
        "success": not has_error,
        "errors": output if has_error else "",
        "warnings": "",
        "message": "Django check failed." if has_error else "Django check passed. Safe to start.",
    }


def _test_html(frontend_dir: str) -> dict:
    """Test plain HTML — verify index.html exists and is non-empty."""

    exit_code, stdout, _ = _sandbox.exec(
        f"test -s {frontend_dir}/index.html && echo OK || echo MISSING"
    )
    if "MISSING" in stdout:
        return {
            "success": False,
            "errors": "index.html is missing or empty.",
            "warnings": "",
            "message": f"No valid index.html in {frontend_dir}.",
        }

    return {
        "success": True,
        "errors": "",
        "warnings": "",
        "message": "index.html found and non-empty.",
    }


# ── Dispatch Map ──────────────────────────────────────────────────────────────

FRAMEWORK_TESTS = {
    "vite":      _test_vite,
    "react_cra": _test_vite,
    "vue":       _test_vite,
    "flask":     _test_flask,
    "django":    _test_django,
    "html":      _test_html,
}


# ── Tool ──────────────────────────────────────────────────────────────────────

@tool
def test_frontend(frontend_dir: str) -> dict:
    """
    Tests a frontend application by auto-detecting its framework and running
    the appropriate validation checks.

    Supports: Vite, React (CRA), Vue, Flask, Django, plain HTML.

    Always call this after writing all frontend files and running install steps,
    before starting the dev or production server.
    Only start the server if this tool returns success=True.

    Args:
        frontend_dir: Absolute path to the frontend directory inside the container.
                      Examples: /workspace/frontend  or  /workspace  (for Flask)

    Returns:
        dict with keys:
            success (bool)    — whether the frontend is safe to run
            framework (str)   — detected framework
            errors (str)      — errors that must be fixed
            warnings (str)    — non-blocking warnings
            message (str)     — summary for the agent
    """
    if _sandbox is None:
        return {
            "success": False,
            "framework": "unknown",
            "errors": "Sandbox not initialized.",
            "warnings": "",
            "message": "Cannot test frontend — sandbox not running.",
        }

    logger.info(f"Testing frontend in: {frontend_dir}")

    framework = _detect_frontend_type(frontend_dir)
    logger.info(f"Framework detected: {framework}")

    test_fn = FRAMEWORK_TESTS.get(framework)

    if test_fn is None:
        return {
            "success": False,
            "framework": framework,
            "errors": f"Unknown framework in {frontend_dir}.",
            "warnings": "",
            "message": "Cannot auto-test this frontend type.",
        }

    result = test_fn(frontend_dir)
    result["framework"] = framework

    if result["success"]:
        logger.info(f"Frontend test passed | framework={framework}")
    else:
        logger.error(f"Frontend test failed | framework={framework} | errors={result['errors'][:200]}")

    return result