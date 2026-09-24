"""
Unit tests for Member 3 - Fixer Agent (src/agents/fixer.py).
Tests contract adherence, input validation, code fence cleaning,
unified diff generation, and retry context incorporation.
"""

import pytest
from unittest.mock import patch

from src.state import DebugState
from src.agents import fixer


def test_fixer_empty_source_code_raises_error():
    """Verify fixer raises clear ValueError when source_code is missing."""
    empty_state: DebugState = {
        "source_code": "",
        "analysis": {"function": "add"},
    }
    with pytest.raises(ValueError, match="Fixer requires source_code"):
        fixer.run(empty_state)


def test_fixer_generates_fixed_code_and_patch_diff():
    """Verify fixer returns fixed_code, unified patch_diff, and updated logs."""
    buggy_code = """def add(a, b):
    # Bug: subtraction instead of addition
    return a - b

def multiply(a, b):
    return a * b
"""
    expected_fixed = """def add(a, b):
    # Fixed: correct addition operator
    return a + b

def multiply(a, b):
    return a * b
"""

    state: DebugState = {
        "file_path": "calculator.py",
        "source_code": buggy_code,
        "analysis": {
            "root_cause": "Function add returns a - b instead of a + b.",
            "file": "calculator.py",
            "function": "add",
            "line_start": 1,
            "line_end": 3,
        },
        "generated_tests": "def test_add(): assert add(1, 2) == 3\n",
        "logs": ["Test Generator completed"],
    }

    mock_llm_json = {
        "fixed_code": expected_fixed
    }

    with patch("src.agents.fixer.call_llm_json", return_value=mock_llm_json):
        result = fixer.run(state)

    # 1. Verify returned keys
    assert set(result.keys()) == {"fixed_code", "patch_diff", "logs"}
    assert result["fixed_code"] == expected_fixed

    # 2. Verify patch_diff is a valid unified diff
    patch_diff = result["patch_diff"]
    assert "--- a/calculator.py" in patch_diff
    assert "+++ b/calculator.py" in patch_diff
    assert "-    return a - b" in patch_diff
    assert "+    return a + b" in patch_diff

    # 3. Verify logs updated
    assert len(result["logs"]) > len(state["logs"])
    assert any("Fixer: generated corrected code" in log for log in result["logs"])


def test_fixer_cleans_markdown_fences():
    """Verify fixer strips markdown ```python code fences if returned by LLM."""
    buggy_code = "def foo(): return False\n"
    fenced_fixed = "```python\ndef foo():\n    return True\n```"

    state: DebugState = {
        "file_path": "foo.py",
        "source_code": buggy_code,
        "analysis": {"function": "foo"},
    }

    mock_response = {"fixed_code": fenced_fixed}

    with patch("src.agents.fixer.call_llm_json", return_value=mock_response):
        result = fixer.run(state)

    assert result["fixed_code"] == "def foo():\n    return True\n"
    assert "```" not in result["fixed_code"]


def test_fixer_incorporates_retry_test_output():
    """Verify fixer includes prior failed verification output in prompt on retry."""
    buggy_code = "def compute(): return 0\n"
    state: DebugState = {
        "file_path": "compute.py",
        "source_code": buggy_code,
        "analysis": {"function": "compute"},
        "test_output": "FAILED: assert compute() == 100",
        "attempts": 1,
        "logs": ["Attempt 0 failed"],
    }

    captured_prompts = []

    def mock_call(sys_prompt, user_prompt):
        captured_prompts.append(user_prompt)
        return {"fixed_code": "def compute(): return 100\n"}

    with patch("src.agents.fixer.call_llm_json", side_effect=mock_call):
        result = fixer.run(state)

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "Previous Verification Failure (Attempt #1)" in prompt
    assert "FAILED: assert compute() == 100" in prompt
    assert result["fixed_code"] == "def compute(): return 100\n"
