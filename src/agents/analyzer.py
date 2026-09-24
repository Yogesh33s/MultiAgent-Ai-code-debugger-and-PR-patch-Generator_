"""
Analyzer Agent:
Diagnoses failing tests, traces root causes in source code,
and produces structured analysis coordinates (file, function, line range).
"""

import os
from typing import Dict, Any

from src.state import DebugState
from src.llm import call_llm_json
from src.tools.code_parser import list_functions, extract_function, extract_all_functions


def _load_prompt() -> str:
    """Load system prompt from src/prompts/analyzer.md with fallback."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "..", "prompts", "analyzer.md")
    
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    # Fallback system prompt if markdown file is unavailable
    return (
        "You are an expert code debugging AI. Analyze the code, error log, and test failure. "
        "Return ONLY a JSON with keys: root_cause, file, function, line_start, line_end."
    )


def run(state: DebugState) -> dict:
    """
    Execute root cause analysis on the provided state.
    
    Args:
        state: Shared DebugState dictionary
        
    Returns:
        Dictionary updating only 'analysis' and 'logs' keys
    """
    source_code = state.get("source_code", "")
    error_log = state.get("error_log", "")
    file_path = state.get("file_path", "unknown_file.py")
    test_output = state.get("test_output", "")
    attempts = state.get("attempts", 0)

    # 1. Parse AST to inspect all available functions and their line numbers
    parsed_functions = extract_all_functions(source_code)
    func_names = [f["name"] for f in parsed_functions]
    func_summary = "\n".join(
        [f"- Function '{f['name']}' (lines {f['line_start']}-{f['line_end']})" for f in parsed_functions]
    )

    # 2. Prepare user prompt with complete context
    user_prompt_sections = [
        f"Target File: {file_path}",
        f"Functions detected in file:\n{func_summary if func_summary else 'No functions detected'}",
        "\n--- Original Failing Test / Error Log ---",
        error_log or "No initial error log provided.",
    ]

    # If this is a retry attempt, include previous test failure details
    if test_output:
        user_prompt_sections.extend([
            f"\n--- Previous Attempt Test Failure (Attempt #{attempts}) ---",
            test_output,
            "Notice: The previous fix attempt did not pass verification. Please revise your root cause analysis.",
        ])

    user_prompt_sections.extend([
        "\n--- Full Source Code ---",
        source_code or "# (Empty source code)",
    ])

    user_prompt = "\n".join(user_prompt_sections)
    system_prompt = _load_prompt()

    # 3. Request root cause analysis from LLM
    try:
        raw_analysis = call_llm_json(system_prompt, user_prompt)
    except Exception as e:
        # Graceful fallback in case of LLM parsing or network issues
        first_func = func_names[0] if func_names else "main"
        raw_analysis = {
            "root_cause": f"Analysis encountered error during LLM call: {e}. Defaulting to inspect first function.",
            "file": file_path,
            "function": first_func,
            "line_start": 1,
            "line_end": 10,
        }

    # 4. Refine line coordinates using tree-sitter AST parser if possible
    detected_func = raw_analysis.get("function", "")
    fn_info = extract_function(source_code, detected_func) if detected_func else None

    # If Tree-sitter found the exact function, ensure line ranges are accurate
    line_start = raw_analysis.get("line_start")
    line_end = raw_analysis.get("line_end")

    if fn_info:
        # Snap to function boundaries if LLM line numbers were missing or invalid
        if not line_start or not line_end or line_start <= 0 or line_end < line_start:
            line_start = fn_info["line_start"]
            line_end = fn_info["line_end"]

    final_analysis = {
        "root_cause": raw_analysis.get("root_cause", "Root cause identified."),
        "file": raw_analysis.get("file", file_path),
        "function": detected_func or (fn_info["name"] if fn_info else "unknown"),
        "line_start": int(line_start) if line_start else 1,
        "line_end": int(line_end) if line_end else 1,
    }

    # 5. Format human-readable log for the live UI
    step_log = (
        f"Analyzer: Found root cause in '{final_analysis['function']}' "
        f"(lines {final_analysis['line_start']}-{final_analysis['line_end']}): "
        f"{final_analysis['root_cause'][:120]}..."
    )

    current_logs = state.get("logs", [])
    updated_logs = current_logs + [step_log]

    return {
        "analysis": final_analysis,
        "logs": updated_logs,
    }
