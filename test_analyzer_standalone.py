"""
Standalone test script for Member 1 (Analyzer & Code Parser).
Runs both tools on a hardcoded state dictionary without needing other agents.
"""

import json
from src.state import DebugState
from src.tools.code_parser import list_functions, extract_function
from src.agents import analyzer


def run_tests():
    print("=" * 60)
    print("STEP 1: Testing Tree-sitter Code Parser")
    print("=" * 60)

    sample_buggy_code = '''def add(a, b):
    return a + b

def sum_list(numbers):
    total = 0
    # BUG: skips last element
    for i in range(len(numbers) - 1):
        total += numbers[i]
    return total

def divide(a, b):
    return a / b
'''

    functions = list_functions(sample_buggy_code)
    print(f"Functions detected: {functions}")
    assert "sum_list" in functions, "sum_list function should be detected"

    fn_info = extract_function(sample_buggy_code, "sum_list")
    print(f"Extracted 'sum_list': lines {fn_info['line_start']} to {fn_info['line_end']}")
    print(f"Code snippet:\n{fn_info['code']}\n")
    assert fn_info["line_start"] == 4, f"Expected start line 4, got {fn_info['line_start']}"
    assert fn_info["line_end"] == 9, f"Expected end line 9, got {fn_info['line_end']}"

    print("=" * 60)
    print("STEP 2: Testing Analyzer Agent with Hardcoded State")
    print("=" * 60)

    # Initial state with failing test log
    initial_state: DebugState = {
        "repo_path": "/demo_bugs/bug1_off_by_one",
        "file_path": "calculator.py",
        "source_code": sample_buggy_code,
        "error_log": (
            "FAILED test_calculator.py::test_sum_list - AssertionError: assert 6 == 10\n"
            "calculator.py:7: in sum_list\n"
            "    total += numbers[i]\n"
            "E   assert 6 == 10"
        ),
        "attempts": 0,
        "max_attempts": 3,
        "logs": ["Initial state loaded"],
    }

    result = analyzer.run(initial_state)

    print("\nAnalyzer output:")
    print(json.dumps(result, indent=2))

    assert "analysis" in result, "Result must contain 'analysis' key"
    assert "logs" in result, "Result must contain 'logs' key"
    assert "root_cause" in result["analysis"], "Analysis must have 'root_cause'"
    assert "function" in result["analysis"], "Analysis must have 'function'"
    assert "line_start" in result["analysis"], "Analysis must have 'line_start'"
    assert "line_end" in result["analysis"], "Analysis must have 'line_end'"

    print("\n" + "=" * 60)
    print("STEP 3: Testing Analyzer Agent on Retry (with test_output)")
    print("=" * 60)

    retry_state: DebugState = {
        **initial_state,
        "attempts": 1,
        "test_output": (
            "pytest output after attempt 1: FAILED test_calculator.py::test_sum_list - assert 6 == 10"
        ),
        "logs": result["logs"] + ["Fixer attempted fix", "Verify: tests failed"],
    }

    retry_result = analyzer.run(retry_state)
    print("\nRetry Analyzer output:")
    print(json.dumps(retry_result, indent=2))

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! Analyzer is working as expected.")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
