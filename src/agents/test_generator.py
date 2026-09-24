import os
import re
from src.state import DebugState
from src.llm import call_llm_json, call_llm


def _clean_code_fences(code_str: str) -> str:
    cleaned = code_str.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:python)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    return cleaned


def run(state: DebugState) -> dict:
    analysis = state.get("analysis", {})
    source_code = state.get("source_code", "")
    file_path = state.get("file_path", "solution.py")

    base_name = os.path.basename(file_path) if file_path else "solution.py"
    module_name = os.path.splitext(base_name)[0]

    prompt = f"""
Generate 3-5 pytest tests that reproduce the identified bug.

Target File: {file_path}
Target Module Name: '{module_name}'

Analysis:
{analysis}

Source code:
{source_code}

The tests must:
- Import functions directly from '{module_name}' (e.g. `from {module_name} import ...` or `import {module_name}`)
- Reproduce the bug in the current code
- Pass after the bug is fixed
- Cover relevant edge cases

Return JSON in this format:
{{
    "tests": "complete pytest code as a string"
}}
"""

    tests_code = ""
    try:
        result = call_llm_json(
            "You are a test-generation expert. Generate precise pytest tests.",
            prompt
        )
        if isinstance(result, dict):
            for k in ["tests", "test_code", "pytest_code", "code"]:
                if result.get(k) and str(result[k]).strip():
                    tests_code = str(result[k])
                    break
    except Exception as e:
        print(f"[test_generator] JSON parsing failed: {e}. Attempting direct code extraction fallback...")

    if not tests_code:
        try:
            raw_text = call_llm(
                "You are a test-generation expert. Output ONLY complete runnable pytest test code.",
                prompt
            )
            cleaned = _clean_code_fences(raw_text)
            if any(kw in cleaned for kw in ["def test_", "import pytest"]):
                tests_code = cleaned
        except Exception:
            pass

    tests_code = _clean_code_fences(tests_code)

    return {
        "generated_tests": tests_code,
        "logs": state.get("logs", []) + ["Test Generator: generated tests"]
    }