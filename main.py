"""
Main CLI entry point for Multi-Agent AI Code Debugger & PR Patch Generator.
Runs the complete LangGraph pipeline through Member 1, Member 2, and Member 3:
Buggy Code -> Analyzer (M1) -> Test Generator (M2) -> Fixer (M3) -> Verify (Pytest) -> Open PR (M3)
"""

import os
import sys
import argparse
from unittest.mock import patch

from src.state import DebugState
from src.graph import build_graph


# Sample fallback buggy code if no file is provided
DEFAULT_BUGGY_CODE = """def sum_list(numbers: list) -> int:
    total = 0
    # BUG: Off-by-one error (range excludes last element)
    for i in range(len(numbers) - 1):
        total += numbers[i]
    return total
"""

DEFAULT_ERROR_LOG = (
    "AssertionError: assert sum_list([1, 2, 3, 4]) == 10 failed (returned 6 instead of 10)"
)


def run_pipeline(source_code: str, error_log: str, file_path: str = "calculator.py", mock: bool = False):
    print("\n" + "=" * 70)
    print("🚀 STARTING MULTI-AGENT DEBUGGER PIPELINE")
    print("=" * 70)
    print(f"Target File : {file_path}")
    print(f"Execution   : {'[OFFLINE MOCK MODE]' if mock else '[LIVE LLM MODE]'}")
    print("-" * 70)

    initial_state: DebugState = {
        "file_path": file_path,
        "source_code": source_code,
        "error_log": error_log,
        "attempts": 0,
        "max_attempts": 3,
        "logs": ["Pipeline initialized"],
    }

    app = build_graph()

    def _execute():
        print("\n⏳ Executing agent workflow...\n")
        final_state = initial_state
        for event in app.stream(initial_state):
            for node_name, node_output in event.items():
                print(f"▶ Step completed: [{node_name}]")
                if "logs" in node_output and node_output["logs"]:
                    print(f"  • Log: {node_output['logs'][-1]}")
                final_state.update(node_output)
        return final_state

    if mock:
        # Mock responses for offline zero-cost testing
        mock_analysis = {
            "root_cause": "Off-by-one defect: range(len(numbers) - 1) excludes final item.",
            "file": file_path,
            "function": "sum_list",
            "line_start": 1,
            "line_end": 7,
        }
        mock_tests = (
            f"from {os.path.splitext(os.path.basename(file_path))[0]} import sum_list\n"
            "def test_sum_list_normal():\n"
            "    assert sum_list([1, 2, 3, 4]) == 10\n"
            "def test_sum_list_single():\n"
            "    assert sum_list([5]) == 5\n"
            "def test_sum_list_empty():\n"
            "    assert sum_list([]) == 0\n"
        )
        mock_fixed = source_code.replace("range(len(numbers) - 1)", "range(len(numbers))")

        def mock_llm_json(system: str, user: str) -> dict:
            if "code repair" in system.lower() or "fixer" in system.lower():
                return {"fixed_code": mock_fixed}
            elif "test-generation" in system.lower():
                return {"tests": mock_tests}
            else:
                return mock_analysis

        with patch("src.agents.analyzer.call_llm_json", side_effect=mock_llm_json), \
             patch("src.agents.test_generator.call_llm_json", side_effect=mock_llm_json), \
             patch("src.agents.fixer.call_llm_json", side_effect=mock_llm_json):
            final_state = _execute()
    else:
        final_state = _execute()

    print("\n" + "=" * 70)
    print("🏁 PIPELINE EXECUTION RESULTS")
    print("=" * 70)
    print(f"Tests Passed : {final_state.get('test_passed', False)}")
    print(f"Total Attempts: {final_state.get('attempts', 0)}")
    print(f"PR URL / Patch : {final_state.get('pr_url', 'None')}")

    if final_state.get("patch_diff"):
        print("\n--- Unified Patch Diff ---")
        print(final_state["patch_diff"])

    if final_state.get("test_output"):
        print("\n--- Test Suite Output ---")
        print(final_state["test_output"])

    print("=" * 70)
    if final_state.get("test_passed"):
        print("🎉 SUCCESS: Bug was isolated, reproduced, repaired, verified, and exported!")
    else:
        print("⚠️ Pipeline ended without passing all tests within maximum attempts.")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent AI Code Debugger CLI")
    parser.add_argument("--file", "-f", type=str, default=None,
                        help="Path to buggy source file")
    parser.add_argument("--repo", "-r", type=str, default=None,
                        help="GitHub repository URL to clone and scan")
    parser.add_argument("--branch", "-b", type=str, default="main",
                        help="Branch name for GitHub repository")
    parser.add_argument("--zip", "-z", type=str, default=None,
                        help="Path to ZIP archive to extract and scan")
    parser.add_argument("--error", "-e", type=str, default=None,
                        help="Error log or stack trace for the bug")
    parser.add_argument("--mock", action="store_true",
                        help="Run in offline mock mode without calling external LLM APIs")
    args = parser.parse_args()

    # Check for API keys if mock is not explicitly passed
    has_keys = any(os.getenv(k) for k in ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"])
    mock_mode = args.mock or not has_keys

    if not args.mock and not has_keys:
        print("ℹ️  No LLM API keys found in environment or .env file.")
        print("ℹ️  Automatically enabling --mock mode for offline testing.\n")

    from src.tools.repo_loader import (
        clone_or_download_repo,
        safe_extract_zip,
        prepare_analyzer_payload,
    )

    workspace = None
    source = ""
    file_path = "solution.py"
    error_log = args.error

    if args.repo:
        print(f"📦 Cloning and scanning GitHub repository: {args.repo} (branch: {args.branch})...")
        workspace, files = clone_or_download_repo(args.repo, args.branch)
        payload = prepare_analyzer_payload(workspace, target_file=args.file, error_log=error_log)
        file_path = payload["file_path"]
        source = payload["source_code"]
        error_log = payload["error_log"]
        print(f"✓ Discovered {len(files)} Python files. Target: {file_path}\n")

    elif args.zip:
        print(f"📦 Extracting and scanning ZIP archive: {args.zip}...")
        workspace, files = safe_extract_zip(args.zip)
        payload = prepare_analyzer_payload(workspace, target_file=args.file, error_log=error_log)
        file_path = payload["file_path"]
        source = payload["source_code"]
        error_log = payload["error_log"]
        print(f"✓ Discovered {len(files)} Python files. Target: {file_path}\n")

    elif args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8") as f:
            source = f.read()
        file_path = os.path.basename(args.file)

        if not error_log:
            file_dir = os.path.dirname(args.file)
            if file_dir and os.path.isdir(file_dir):
                test_files = [
                    os.path.join(file_dir, f)
                    for f in os.listdir(file_dir)
                    if f.startswith("test_") and f.endswith(".py")
                ]
                if test_files:
                    import subprocess
                    test_file = test_files[0]
                    print(f"🔍 Auto-running companion test suite: {test_file}...")
                    proc = subprocess.run(
                        [sys.executable, "-m", "pytest", os.path.basename(test_file)],
                        cwd=file_dir,
                        capture_output=True,
                        text=True,
                    )
                    error_log = (proc.stdout + proc.stderr).strip()
                    print(f"📋 Captured error log ({len(error_log.splitlines())} lines).\n")
    else:
        # Default demo file if nothing specified
        demo_file = "demo_bugs/bug1_off_by_one/calculator.py"
        if os.path.exists(demo_file):
            with open(demo_file, "r", encoding="utf-8") as f:
                source = f.read()
            file_path = "calculator.py"
        else:
            source = DEFAULT_BUGGY_CODE
            file_path = "calculator.py"

    if not error_log:
        error_log = DEFAULT_ERROR_LOG

    run_pipeline(source_code=source, error_log=error_log, file_path=file_path, mock=mock_mode)


if __name__ == "__main__":
    main()
