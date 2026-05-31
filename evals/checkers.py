"""Output checkers for eval harness.

Each checker receives an output string and returns (passed: bool, reason: str).
"""

from typing import Callable

_ERROR_SIGNALS = (
    "sorry, i can't",
    "sorry, i cannot",
    "i cannot help",
    "unable to help",
    "i can't help with",
    "[error",
    "error:",
    "i'm not able",
)


def check_contains_code(output: str, spec: dict) -> tuple[bool, str]:
    """Pass if output contains a code block."""
    has_block = "```" in output
    has_indent_code = any(
        line.startswith("    ") and ("def " in line or "return " in line or "import " in line or "class " in line)
        for line in output.splitlines()
    )
    if has_block or has_indent_code:
        return True, "contains code block"
    return False, "no code block found"


def check_contains_any(output: str, spec: dict) -> tuple[bool, str]:
    """Pass if output contains at least one of the given values (case-sensitive)."""
    values = spec.get("values", [])
    for v in values:
        if v in output:
            return True, f"found '{v}'"
    return False, f"none of {values} found in output"


def check_no_error(output: str, spec: dict) -> tuple[bool, str]:
    """Pass if output doesn't contain error signals."""
    low = output.lower()
    for sig in _ERROR_SIGNALS:
        if sig in low:
            return False, f"error signal found: '{sig}'"
    return True, "no error signals"


def check_min_length(output: str, spec: dict) -> tuple[bool, str]:
    """Pass if output is at least N chars."""
    min_len = spec.get("value", 50)
    length = len(output.strip())
    if length >= min_len:
        return True, f"length {length} >= {min_len}"
    return False, f"too short: {length} < {min_len}"


_CHECKER_MAP: dict[str, Callable] = {
    "contains_code": check_contains_code,
    "contains_any": check_contains_any,
    "no_error": check_no_error,
    "min_length": check_min_length,
}


def run_checks(output: str, checks: list[dict]) -> list[dict]:
    """Run all checks for an eval task. Returns list of {type, passed, reason}."""
    results = []
    for spec in checks:
        check_type = spec.get("type", "")
        fn = _CHECKER_MAP.get(check_type)
        if fn is None:
            results.append({"type": check_type, "passed": False, "reason": f"unknown checker: {check_type}"})
            continue
        try:
            passed, reason = fn(output, spec)
        except Exception as e:
            passed, reason = False, f"checker error: {e}"
        results.append({"type": check_type, "passed": passed, "reason": reason})
    return results


def all_passed(check_results: list[dict]) -> bool:
    return all(r["passed"] for r in check_results)
