from langgraph.graph import StateGraph, END
from src.state import DebugState
from src.agents import analyzer, test_generator, fixer
from src.tools.test_runner import run_tests
from src.tools.git_pr import open_pr

def verify(state: DebugState) -> dict:
    passed, output = run_tests(state)
    return {
        "test_passed": passed,
        "test_output": output,
        "attempts": state.get("attempts", 0) + 1,
        "error_log": output if not passed else state.get("error_log", ""),
    }

def pr_node(state: DebugState) -> dict:
    return {"pr_url": open_pr(state)}

def route_after_verify(state: DebugState) -> str:
    if state["test_passed"]:
        return "open_pr"
    if state["attempts"] >= state.get("max_attempts", 3):
        return "give_up"
    return "analyzer"          # fallback to step 1

def build_graph():
    g = StateGraph(DebugState)
    g.add_node("analyzer", analyzer.run)
    g.add_node("test_generator", test_generator.run)
    g.add_node("fixer", fixer.run)
    g.add_node("verify", verify)
    g.add_node("open_pr", pr_node)

    g.set_entry_point("analyzer")
    g.add_edge("analyzer", "test_generator")
    g.add_edge("test_generator", "fixer")
    g.add_edge("fixer", "verify")
    g.add_conditional_edges("verify", route_after_verify,
        {"open_pr": "open_pr", "analyzer": "analyzer", "give_up": END})
    g.add_edge("open_pr", END)
    return g.compile()