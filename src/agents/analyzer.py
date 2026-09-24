from src.state import DebugState

def run(state: DebugState) -> dict:
    """Return ONLY the keys this agent updates."""
    return {
        "analysis": {
            "root_cause": "FAKE: operator is wrong",
            "file": state.get("file_path", ""),
            "function": "add",
            "line_start": 2,
            "line_end": 2,
        },
        "logs": state.get("logs", []) + ["Analyzer: found root cause (stub)"],
    }