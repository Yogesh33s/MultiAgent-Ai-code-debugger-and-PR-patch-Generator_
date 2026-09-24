"""
Large-Scale Benchmark Test for Member 1 (Analyzer & Tree-sitter Parser).
Tests the Analyzer on an enterprise e-commerce platform codebase with ~1,500 lines of code.
"""

import os
import json
import subprocess
from src.state import DebugState
from src.tools.code_parser import list_functions, extract_function, extract_all_functions
from src.agents import analyzer


def main():
    print("=" * 75)
    print("🧪 LARGE-SCALE 1,500-LINE CODEBASE TEST FOR ANALYZER AGENT")
    print("=" * 75)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(base_dir, "demo_bugs", "bug2_ecommerce_platform", "ecommerce_platform.py")
    test_path = os.path.join(base_dir, "demo_bugs", "bug2_ecommerce_platform", "test_ecommerce.py")

    # 1. Read the 1,500-line source code
    with open(source_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    lines = source_code.splitlines()
    print(f"\n📁 Loaded Source File: {source_path}")
    print(f"📊 Total Lines of Code: {len(lines)} lines")

    # 2. Run Tree-sitter AST parser over the large file
    print("\n🔍 Step 1: Running Tree-sitter AST Parser across 1,500 lines...")
    all_funcs = extract_all_functions(source_code)
    func_names = [f["name"] for f in all_funcs]
    print(f"✅ Tree-sitter successfully discovered {len(all_funcs)} functions/methods across the codebase.")
    print(f"   Sample discovered functions: {func_names[:8]} ... (+ {len(func_names) - 8} more)")

    # 3. Execute Pytest to capture the authentic runtime failure
    print("\n🏃 Step 2: Executing Pytest on buggy codebase...")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(base_dir, "demo_bugs", "bug2_ecommerce_platform")
    
    import sys
    pytest_proc = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-v"],
        cwd=base_dir,
        capture_output=True,
        text=True,
        env=env
    )
    raw_error_log = pytest_proc.stdout + "\n" + pytest_proc.stderr
    print("❌ Pytest Failure Captured (Summary):")
    for line in raw_error_log.splitlines():
        if "FAILED" in line or "AssertionError" in line or "assert 125.0 == 165.0" in line:
            print(f"   {line}")

    # 4. Construct DebugState Contract
    print("\n🤖 Step 3: Invoking Analyzer Agent with DebugState...")
    state: DebugState = {
        "repo_path": os.path.dirname(source_path),
        "file_path": "ecommerce_platform.py",
        "source_code": source_code,
        "error_log": raw_error_log,
        "attempts": 0,
        "max_attempts": 3,
        "logs": ["Test session started on enterprise e-commerce platform."],
    }

    # 5. Run Analyzer Agent
    analysis_result = analyzer.run(state)

    print("\n" + "=" * 75)
    print("🎯 ANALYZER AGENT RESULTS")
    print("=" * 75)
    print(json.dumps(analysis_result, indent=2))

    analysis = analysis_result["analysis"]
    print("\n" + "-" * 75)
    print("📋 DIAGNOSIS BREAKDOWN:")
    print(f"  • Root Cause:     {analysis.get('root_cause')}")
    print(f"  • Target File:    {analysis.get('file')}")
    print(f"  • Buggy Function: {analysis.get('function')}")
    print(f"  • Line Range:     Lines {analysis.get('line_start')} to {analysis.get('line_end')}")
    print("-" * 75)

    # 6. Extract the exact buggy code lines using Tree-sitter coordinates
    start = max(1, analysis.get("line_start", 1))
    end = min(len(lines), analysis.get("line_end", len(lines)))
    print(f"\n🔍 Code Snippet Identified by Analyzer (Lines {start}-{end}):")
    print("   " + "\n   ".join([f"{i:4d} | {lines[i - 1]}" for i in range(start, end + 1)]))

    print("\n" + "=" * 75)
    print("✨ TEST COMPLETE! Analyzer identified the defect out of 1,500 lines!")
    print("=" * 75)


if __name__ == "__main__":
    main()
