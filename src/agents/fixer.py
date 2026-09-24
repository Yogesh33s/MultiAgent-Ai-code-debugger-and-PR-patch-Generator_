"""
Fixer Agent:
Generates complete corrected source code based on root cause analysis,
reproducing tests, and test runner feedback. Computes unified patch diff.
"""

import os
import re
import difflib
from typing import Dict, Any

from src.state import DebugState
from src.llm import call_llm_json


def _load_prompt() -> str:
    """Load system prompt from src/prompts/fixer.md."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "..", "prompts", "fixer.md")

    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    return (
        "You are an expert automated code repair AI agent. "
        "Fix the identified bug and return ONLY a JSON object: {\"fixed_code\": \"...\"}."
    )


def _clean_code_fences(code_str: str) -> str:
    """Strip markdown code block fences if present in the LLM string."""
    cleaned = code_str.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:python)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


def run(state: DebugState) -> dict:
    """
    Execute bug fix generation using root cause analysis and reproducing tests.

    Args:
        state: Shared DebugState dictionary. Requires 'source_code'.

    Returns:
        Dictionary updating ONLY 'fixed_code', 'patch_diff', and 'logs' keys:
        {
            "fixed_code": str,
            "patch_diff": str,
            "logs": List[str]
        }
    """
    source_code = state.get("source_code", "")
    if not source_code or not source_code.strip():
        raise ValueError("Fixer requires source_code in DebugState.")

    analysis = state.get("analysis", {})
    generated_tests = state.get("generated_tests", "")
    test_output = state.get("test_output", "")
    file_path = state.get("file_path", "solution.py")
    attempts = state.get("attempts", 0)

    # 1. Construct prompt sections for LLM
    prompt_sections = [
        f"Target File: {file_path}",
        f"\n--- Root Cause Analysis ---",
        f"Function : {analysis.get('function', 'unknown')}",
        f"Lines    : {analysis.get('line_start', '?')} to {analysis.get('line_end', '?')}",
        f"Diagnosis: {analysis.get('root_cause', 'Defect identified in source code.')}",
    ]

    if generated_tests and generated_tests.strip():
        prompt_sections.extend([
            "\n--- Reproducing Pytest Tests (Must Pass on Fixed Code) ---",
            generated_tests,
        ])

    if test_output and test_output.strip():
        prompt_sections.extend([
            f"\n--- Previous Verification Failure (Attempt #{attempts}) ---",
            test_output,
            "Notice: The prior fix attempt failed tests. Review the failure above and fix the issue properly.",
        ])

    prompt_sections.extend([
        "\n--- Original Source Code ---",
        source_code,
    ])

    user_prompt = "\n".join(prompt_sections)
    system_prompt = _load_prompt()

    # 2. Call LLM to generate the full corrected code
    try:
        result = call_llm_json(system_prompt, user_prompt)
    except Exception as e:
        raise RuntimeError(f"Fixer LLM call failed: {e}")

    raw_fixed_code = result.get("fixed_code")
    if not raw_fixed_code or not str(raw_fixed_code).strip():
        raise ValueError(f"Fixer received invalid LLM response: missing or empty 'fixed_code' in {result}")

    fixed_code = _clean_code_fences(str(raw_fixed_code))

    # 3. Compute unified diff using difflib
    orig_lines = source_code.splitlines(keepends=True)
    fixed_lines = fixed_code.splitlines(keepends=True)
    base_name = os.path.basename(file_path) if file_path else "solution.py"

    diff = list(difflib.unified_diff(
        orig_lines,
        fixed_lines,
        fromfile=f"a/{base_name}",
        tofile=f"b/{base_name}",
    ))
    patch_diff = "".join(diff)

    # 4. Append log
    step_log = (
        f"Fixer: generated corrected code for '{base_name}' "
        f"({len(fixed_lines)} lines, {len(diff)} diff lines)"
    )
    current_logs = state.get("logs", [])
    updated_logs = current_logs + [step_log]

    return {
        "fixed_code": fixed_code,
        "patch_diff": patch_diff,
        "logs": updated_logs,
    }
