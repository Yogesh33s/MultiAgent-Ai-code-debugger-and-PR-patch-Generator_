"""
Standalone test script for Member 3 (Fixer Agent & Git PR Tool).
Runs Fixer and git_pr on a hardcoded state dictionary without needing other agents.
"""

import os
from unittest.mock import patch
from src.state import DebugState
from src.agents import fixer
from src.tools import git_pr


def main():
    print("=" * 65)
    print("🛠️ TESTING MEMBER 3: FIXER AGENT & GIT PR TOOL")
    print("=" * 65)

    # 1. Define hardcoded buggy code and state from previous agent steps
    buggy_source = '''def calculate_cart_total(items):
    total = 0
    # BUG: range(len(items) - 1) skips the final cart item
    for i in range(len(items) - 1):
        total += items[i]
    return total
'''

    state: DebugState = {
        "file_path": "cart.py",
        "source_code": buggy_source,
        "analysis": {
            "root_cause": "Off-by-one error: range(len(items) - 1) skips the final cart item.",
            "file": "cart.py",
            "function": "calculate_cart_total",
            "line_start": 1,
            "line_end": 6,
        },
        "generated_tests": (
            "from cart import calculate_cart_total\n"
            "def test_cart_total(): assert calculate_cart_total([10, 20, 30]) == 60\n"
        ),
        "test_output": "FAILED test_cart.py::test_cart_total - assert 30 == 60",
        "attempts": 1,
        "max_attempts": 3,
        "logs": [
            "Analyzer: identified root cause in calculate_cart_total",
            "Test Generator: generated tests",
        ],
    }

    # 2. Run Fixer Agent
    print("\nStep 1: Running Fixer Agent...")
    corrected_code = '''def calculate_cart_total(items):
    total = 0
    # FIXED: iterate through all items in cart
    for i in range(len(items)):
        total += items[i]
    return total
'''

    mock_fixer_response = {
        "fixed_code": corrected_code
    }

    with patch("src.agents.fixer.call_llm_json", return_value=mock_fixer_response):
        fixer_output = fixer.run(state)

    print("\n--- Fixer Output ---")
    print("Fixed Code:\n", fixer_output["fixed_code"])
    print("Patch Diff:\n", fixer_output["patch_diff"])
    print("Updated Logs:")
    for log in fixer_output["logs"]:
        print(" •", log)

    # Update state with fixer outputs
    state.update(fixer_output)

    # 3. Run Git PR Tool (Fallback mode without GITHUB_TOKEN)
    print("\n" + "=" * 65)
    print("Step 2: Running Git PR Tool (Local Patch Fallback)...")
    pr_result = git_pr.open_pr(state)
    print("Result:", pr_result)
    assert os.path.exists(pr_result), f"Patch file {pr_result} should exist"

    with open(pr_result, "r", encoding="utf-8") as f:
        saved_patch = f.read()
    print("\nSaved Patch Content in output/fix.patch:")
    print(saved_patch)

    print("=" * 65)
    print("✨ ALL CHECKS PASSED: Member 3 is working properly!")
    print("=" * 65)


if __name__ == "__main__":
    main()
