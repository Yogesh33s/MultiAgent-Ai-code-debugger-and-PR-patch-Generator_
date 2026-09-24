# 🤖 Multi-Agent AI Code Debugger & PR Patch Generator

An autonomous multi-agent pipeline built with **Python**, **LangGraph**, **Tree-sitter**, and **LLMs** that ingests buggy source code and error logs, pinpoints defect root causes, synthesizes reproducing pytest suites, applies surgical repairs, verifies fixes in an isolated runtime, and automatically opens GitHub Pull Requests or outputs unified git patches.

---

## 🔄 System Architecture

```text
Buggy Code + Error Log
        │
        ▼
┌──────────────────┐
│  Analyzer Agent  │ ◄────────────────────────────────────────────────────┐
│   (Member 1)     │                                                      │
└────────┬─────────┘                                                      │
         │ (analysis: file, func, lines, root_cause)                      │
         ▼                                                                │
┌──────────────────┐                                                      │
│  Test Generator  │                                                      │
│   (Member 2)     │                                                      │
└────────┬─────────┘                                                      │
         │ (generated_tests: 3-5 pytest cases)                            │
         ▼                                                                │
┌──────────────────┐                                                      │
│   Fixer Agent    │                                                      │
│   (Member 3)     │                                                      │
└────────┬─────────┘                                                      │
         │ (fixed_code, patch_diff)                                       │
         ▼                                                                │
┌──────────────────┐        FAIL (attempts < max_attempts)                │
│ Verify (Pytest)  ├──────────────────────────────────────────────────────┘
└────────┬─────────┘
         │ PASS
         ▼
┌──────────────────┐
│   Open PR Node   │ ──► GitHub Pull Request (or fallback to output/fix.patch)
│   (Member 3)     │
└──────────────────┘
```

The entire system is orchestrated by a state graph in [`src/graph.py`](src/graph.py), passing an immutable shared contract **`DebugState`** defined in [`src/state.py`](src/state.py).

---

## 👥 Team Split & Status

| Role | Member | Responsibilities | Files Owned | Status |
|---|---|---|---|:---:|
| **Analyzer Agent** | **Member 1** | AST parsing, Tree-sitter function boundary snapping, root-cause diagnosis, retry analysis | `src/agents/analyzer.py`<br>`src/tools/code_parser.py`<br>`src/prompts/analyzer.md`<br>`tests/test_analyzer.py`<br>`tests/test_code_parser.py` | **✅ COMPLETED** |
| **Test Generator & Runner** | **Member 2** | Synthesize reproducing pytest test cases, isolated temporary execution sandbox | `src/agents/test_generator.py`<br>`src/tools/test_runner.py`<br>`src/prompts/test_generator.md` | **✅ COMPLETED** |
| **Fixer & PR Generator** | **Member 3** | Surgical code repair, unified diff computation, GitHub PR opening with local patch fallback | `src/agents/fixer.py`<br>`src/tools/git_pr.py`<br>`src/prompts/fixer.md`<br>`tests/test_fixer.py`<br>`tests/test_git_pr.py`<br>`test_fixer_standalone.py` | **✅ COMPLETED** |
| **LangGraph Orchestrator** | **Core / Pipeline** | StateGraph compilation, cyclical retry routing, verification node | `src/graph.py`<br>`src/state.py`<br>`src/llm.py` | **✅ COMPLETED** |
| **UI & Visualization** | **Member 4** | Gradio web UI, interactive diff viewer, live agent progress | `app.py` | ⏳ In Progress |

---

## 📦 Shared State Contract (`src/state.py`)

All agents communicate exclusively through `DebugState`:

```python
class DebugState(TypedDict, total=False):
    file_path: str          # Path to the source file being debugged
    source_code: str        # Original buggy code
    error_log: str          # Error stack trace or failure log
    analysis: dict          # Root cause analysis from Member 1
    generated_tests: str    # Pytest test cases from Member 2
    fixed_code: str         # Corrected code from Member 3
    patch_diff: str         # Unified diff between source and fix
    test_passed: bool       # Verification status from pytest runner
    test_output: str        # Stdout/stderr from pytest execution
    attempts: int           # Current debug/repair iteration
    max_attempts: int       # Maximum retry budget (default 3)
    pr_url: str             # GitHub PR URL or path to local patch
    logs: list[str]         # Running timeline of agent actions
```

---

## 🔍 Member Deliverables Breakdown

### 1️⃣ Member 1 — Analyzer Agent
- **Tree-sitter Code Parser ([`src/tools/code_parser.py`](src/tools/code_parser.py))**:
  - Parses Python source files into concrete syntax trees using `tree-sitter-python`.
  - Implements fallback to Python's standard `ast` module if native bindings are unavailable.
  - Extracts 1-indexed start and end line coordinates for classes, sync/async functions, and decorated methods.
- **System Prompt ([`src/prompts/analyzer.md`](src/prompts/analyzer.md))**:
  - Directs the LLM to inspect stack traces, exception messages, code logic, and previous test failure outputs.
  - Enforces strict JSON output conforming to `{root_cause, file, function, line_start, line_end}`.
- **Agent Node ([`src/agents/analyzer.py`](src/agents/analyzer.py))**:
  - Implements `run(state: DebugState) -> dict`.
  - Combines LLM deduction with Tree-sitter verification to guarantee valid file boundaries.
  - Appends diagnostic updates to `state["logs"]`.

### 2️⃣ Member 2 — Test Generator & Runner
- **Test Generator Prompt ([`src/prompts/test_generator.md`](src/prompts/test_generator.md))**:
  - Instructs LLM to generate 3–5 targeted pytest test cases based on root-cause analysis and original code.
  - Requires tests to reproduce the failure on unpatched code, pass when resolved, and assert edge cases.
- **Test Generator Agent ([`src/agents/test_generator.py`](src/agents/test_generator.py))**:
  - Generates full executable test code strings and populates `state["generated_tests"]`.
- **Isolated Pytest Runner ([`src/tools/test_runner.py`](src/tools/test_runner.py))**:
  - Executes tests inside a secure, clean `tempfile.TemporaryDirectory`.
  - Prioritizes `state["fixed_code"]` when evaluating repairs (falls back to `state["source_code"]`).
  - Executes `[sys.executable, "-m", "pytest", "-q"]` with a 20-second timeout to avoid infinite loops.
  - Returns `tuple[bool, str]` indicating pass/fail status and output logs.

### 3️⃣ Member 3 — Fixer Agent & PR Generator
- **Fixer Prompt ([`src/prompts/fixer.md`](src/prompts/fixer.md))**:
  - Instructs the LLM to generate the complete corrected file.
  - Demands surgical modifications that fix the identified bug while preserving all comments, type hints, and unbuggy logic.
- **Fixer Agent ([`src/agents/fixer.py`](src/agents/fixer.py))**:
  - Uses `state["analysis"]`, `state["source_code"]`, `state["generated_tests"]`, and previous `state["test_output"]` on retry attempts.
  - Cleans markdown fences (`python ... `) automatically.
  - Calculates unified diff using `difflib.unified_diff(fromfile=..., tofile=...)`.
  - Returns updated `fixed_code`, `patch_diff`, and logs.
- **Git PR Tool ([`src/tools/git_pr.py`](src/tools/git_pr.py))**:
  - **GitHub Integration**: Authenticates via `GITHUB_TOKEN`, creates a new branch (`fix/<func>-<timestamp>`), commits the patched file, and opens a Pull Request with a formatted summary.
  - **Local Patch Fallback**: If no GitHub token or repository is configured (e.g., local hackathon testing / offline demos), writes the unified diff to `output/fix.patch` and saves `output/fixed_<file>`.
- **Standalone Test Harness ([`test_fixer_standalone.py`](test_fixer_standalone.py))**:
  - Exercises the Fixer Agent and PR tool end-to-end with a hardcoded buggy state.

---

## 🚀 Getting Started

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/bhaveshk25/MultiAgent-Ai-code-debugger-and-PR-patch-Generator.git
cd MultiAgent-Ai-code-debugger-and-PR-patch-Generator

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the project root:
```bash
# LLM Provider Configuration (OpenAI, Gemini, Groq, OpenRouter, Ollama)
OPENAI_API_KEY=your_llm_api_key_here
LLM_MODEL=gpt-4o-mini  # or gemini-2.0-flash, llama-3.3-70b-versatile, etc.
# LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/ # optional

# GitHub Integration (Optional - falls back to output/fix.patch if omitted)
GITHUB_TOKEN=your_github_token_here
GITHUB_REPO=username/repository-name
```

---

## 🧪 Testing & Verification

### Run the Full Automated Test Suite (23 Passing Tests)
```bash
PYTHONPATH=. pytest tests/ -v
```
**Test Coverage Includes:**
- `tests/test_code_parser.py`: Tree-sitter parsing, function extraction, class methods, async & decorated functions, syntax errors.
- `tests/test_analyzer.py`: Empty source detection, missing error log handling, AST coordinate snapping, multi-attempt retries.
- `tests/test_fixer.py`: Code repair generation, unified diff generation, markdown fence stripping, retry with previous failure log.
- `tests/test_git_pr.py`: GitHub PR opening, mocked API failure fallback, local patch file generation.

### Run Member 3 Standalone Harness
```bash
PYTHONPATH=. python test_fixer_standalone.py
```

### Programmatic Multi-Agent Pipeline Execution
```python
from src.graph import build_graph
from src.state import DebugState

# 1. Compile the LangGraph pipeline
app = build_graph()

# 2. Define initial buggy state
initial_state: DebugState = {
    "file_path": "calculator.py",
    "source_code": """def calculate_cart(items):
    total = 0
    for i in range(len(items) - 1): # bug: skips last item
        total += items[i]
    return total
""",
    "error_log": "AssertionError: assert calculate_cart([10, 20, 30]) == 60 (got 30)",
    "attempts": 0,
    "max_attempts": 3,
    "logs": ["Initial state initialized"],
}

# 3. Stream pipeline execution
for event in app.stream(initial_state):
    for node, output in event.items():
        print(f"✅ Node [{node}] finished.")
        if "logs" in output:
            print(f"   Log: {output['logs'][-1]}")
```
