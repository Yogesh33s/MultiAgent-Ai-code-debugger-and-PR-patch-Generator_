# 🤖 Multi-Agent AI Code Debugger & PR Patch Generator

An autonomous multi-agent pipeline that debugs software defects, generates reproducing test cases, produces surgical code fixes, verifies them against test suites, and opens pull requests automatically.

---

## 🔄 System Architecture

```text
                  User / Gradio UI
                         │
                         ▼
                Analyzer (Member 1)
                         │
                         ▼
             Test-Generator (Member 2)
                         │
                         ▼
                Test Runner (Pytest)
                         │
                         ▼
                  Fixer (Member 3)
                         │
                         ▼
                 Verify (Pytest)
                         │
                 ┌───────┴───────┐
                 │               │
          [Fail: Retry]    [Pass: Open PR]
                 │               │
                 ▼               ▼
        Analyzer (Re-eval)   GitHub PR
```

Every agent interacts via a single frozen contract: **`DebugState`** in [`src/state.py`](src/state.py).

---

## 🛠️ Tech Stack

- **Python 3.10+** - Core language
- **LangGraph** - State machine & multi-agent workflow orchestration
- **Tree-sitter & Tree-sitter-python** - AST code parsing & coordinate extraction
- **Gradio** - Interactive web interface
- **Pytest** - Automated test execution & verification runner
- **OpenAI-compatible LLM APIs** - Multi-provider support (Groq, Gemini, OpenRouter, Ollama)
- **GitHub API / PyGithub** - Automated branch creation, patch commits, and Pull Requests

---

## 👥 Team Split & Responsibilities

| Role | Member | Responsibilities | Files Owned | Status |
|---|---|---|---|:---:|
| **Analyzer Agent** | **Member 1** | AST parsing, root-cause diagnosis, coordinate extraction, retry analysis | `src/agents/analyzer.py`<br>`src/tools/code_parser.py`<br>`src/prompts/analyzer.md`<br>`tests/test_analyzer.py`<br>`tests/test_code_parser.py` | **✅ Completed** |
| **Test Generator & Runner** | **Member 2** | Generate 3–5 reproducing pytest cases, subprocess test runner, timeout handling | `src/agents/test_generator.py`<br>`src/tools/test_runner.py`<br>`src/prompts/test_generator.md` | **✅ Completed** |
| **Fixer + PR** | **Member 3** | Unified diff generation, patch application, GitHub PR creation | `src/agents/fixer.py`<br>`src/tools/git_pr.py`<br>`src/prompts/fixer.md` | ⏳ In Progress |
| **UI & Graph** | **Member 4** | Gradio web UI and LangGraph loop orchestrator | `app.py`<br>`src/graph.py` | ⏳ In Progress |
| **Lead / Architecture** | **Lead** | Skeleton, frozen state dictionary, shared LLM helpers | `src/state.py`<br>`src/llm.py`<br>`src/config.py`<br>`main.py` | **✅ Ready** |

---

## 🔍 Completed Components

### 1. Analyzer Agent (`src/agents/analyzer.py`)
The Analyzer Agent diagnoses bugs from source code and error telemetry:
- Reads the source code, error logs, file path, and optional previous test failure outputs (for retry loops).
- Discovers candidate functions using Tree-sitter AST analysis.
- Combines AST function discovery with LLM reasoning to identify the root cause without hallucinating function names.
- Snaps coordinates to Tree-sitter verified 1-indexed `line_start` and `line_end` bounds.
- Returns structured JSON adhering to the `DebugState` contract:
  ```json
  {
    "root_cause": "The add function uses subtraction (-) instead of addition (+)",
    "file": "calculator.py",
    "function": "add",
    "line_start": 1,
    "line_end": 2
  }
  ```
- Supports retry attempts by incorporating previous test execution outputs.
- System prompt centrally loaded and managed in [`src/prompts/analyzer.md`](src/prompts/analyzer.md).

### 2. Code Parser (`src/tools/code_parser.py`)
The code parser analyzes Python source code using Tree-sitter:
- Built with `tree-sitter` and `tree-sitter-python` to parse Python code into an AST.
- Includes automatic fallback to Python's native `ast` module for seamless environment portability.
- **`list_functions(source_code)`**: Discovers all function names defined in the target file.
- **`extract_function(source_code, function_name)`**: Extracts exact code body and 1-indexed `line_start` and `line_end` bounds (including decorated functions and async definitions).
- **`extract_all_functions(source_code)`**: Extracts all functions and their line coordinates.

```python
from src.tools.code_parser import list_functions, extract_function

functions = list_functions(source_code)
# Example: ['add', 'subtract', 'multiply']

result = extract_function(source_code, "add")
# Example: {'code': 'def add(a, b):\n    return a - b', 'line_start': 1, 'line_end': 2}
```

### 3. Test Generator Agent (`src/agents/test_generator.py`)
The Test Generator Agent produces targeted `pytest` test cases to reproduce and isolate defects:
- Ingests the Analyzer output (`state["analysis"]`) and `source_code`.
- System prompt configured in [`src/prompts/test_generator.md`](src/prompts/test_generator.md).
- Generates 3–5 targeted pytest tests designed to:
  - Reproduce the identified bug.
  - Fail on the buggy source code.
  - Pass after the bug is fixed.
  - Cover relevant edge cases and boundary inputs.
- Returns the generated test suite via the shared state (`state["generated_tests"]`) and appends human-readable progress updates to `state["logs"]`.

Example generated tests:
```python
import pytest
from calculator import add

def test_add_positive():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-2, -3) == -5

def test_add_zero():
    assert add(0, 0) == 0
```

### 4. Test Runner Tool (`src/tools/test_runner.py`)
The Test Runner executes tests in a safe, isolated environment:
- Creates an isolated temporary directory (`tempfile.TemporaryDirectory`).
- Dynamically writes the source code file and generated tests into `test_generated.py`.
- Executes `pytest -q` via `subprocess.run`.
- Enforces a 20-second timeout safeguard to protect against infinite loops or hanging tests.
- Returns execution status and output:
  - `passed: bool` (whether all tests passed).
  - `output: str` (combined stdout and stderr).

```python
from src.tools.test_runner import run_tests

passed, output = run_tests(state)
```

Verified test scenarios:
- **Buggy code** → tests fail (`passed = False`).
- **Fixed code** → tests pass (`passed = True`).
- **Long-running / hanging tests** → cleanly times out after 20 seconds.

---

## ⚡ Multi-Provider LLM Configuration (`src/llm.py`)

The project supports multiple LLM providers through a unified OpenAI-compatible client interface in `src/llm.py`. If a provider is not configured or fails, the system automatically falls back to the next available provider.

**Supported providers:**
- **Groq** (`openai/gpt-oss-120b`)
- **Gemini** (`gemini-2.5-flash`)
- **OpenRouter** (`meta-llama/llama-3.3-70b-instruct:free`)
- **Ollama** (`qwen2.5-coder:7b` - offline local model)

```python
PROVIDERS = [
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b"
    },
    {
        "name": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash"
    },
    {
        "name": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model": "meta-llama/llama-3.3-70b-instruct:free"
    },
    {
        "name": "ollama",
        "base_url": "http://localhost:11434/v1",
        "key_env": None,
        "model": "qwen2.5-coder:7b"
    }
]
```

---

## 🔄 Current Pipeline Status

```text
[ ✅ Completed Pipeline ]
    Source Code + Error Log
               │
               ▼
        Analyzer Agent (Member 1)
               │
               ▼
     Test Generator Agent (Member 2)
               │
               ▼
        Test Runner Tool (Pytest)
         ├── Tests Fail (Expected on buggy code)
         └── Tests Pass (Upon bug resolution)

[ ⏳ In Progress Integration ]
       Fixer Agent (Member 3)
               │
               ▼
       Verify (Pytest Retry Loop)
               │
               ▼
      LangGraph State Workflow
               │
               ▼
       Gradio Web UI (Member 4)
               │
               ▼
      GitHub Pull Request Automation
```

The **Analyzer → Test Generator → Test Runner** flow has been successfully tested and verified on buggy and fixed code samples.

---

## 🚀 Getting Started

### 1. Set Up Environment
```bash
# Clone the repository
git clone <your-repository-url>
cd MultiAgent-Ai-code-debugger-and-PR-patch-Generator

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys
Create a `.env` file in the project root:
```env
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key

# For local offline Ollama:
USE_OLLAMA=1
```

> [!CAUTION]
> **Security Notice**: Never commit `.env` or real API keys to GitHub. Real credentials belong in `.env` (ignored by git), while `.env.example` is reserved strictly for dummy template values.

---

## 🧪 Testing & Verification

### 1. Compile Check
```bash
python -m py_compile src/agents/analyzer.py src/agents/test_generator.py src/tools/test_runner.py
```

### 2. Run Test Suite
```bash
pytest tests/test_analyzer.py
```

### 3. Direct Python Usage Example
```python
from src.state import DebugState
from src.agents import analyzer, test_generator
from src.tools.test_runner import run_tests

# 1. Initialize state with buggy code
state: DebugState = {
    "file_path": "calculator.py",
    "source_code": """def add(a, b):
    # Bug: uses subtraction instead of addition
    return a - b
""",
    "error_log": "AssertionError: assert add(2, 3) == 5 failed (got -1)",
    "attempts": 0,
    "max_attempts": 3,
    "logs": ["Starting debugging process"],
}

# 2. Run Analyzer Agent (Member 1)
analysis_result = analyzer.run(state)
state.update(analysis_result)
print("Analysis:", state["analysis"])

# 3. Run Test Generator Agent (Member 2)
tests_result = test_generator.run(state)
state.update(tests_result)
print("Generated Tests:\n", state["generated_tests"])

# 4. Run Test Runner Tool (Member 2)
passed, output = run_tests(state)
print("Tests Passed:", passed)
print("Pytest Output:\n", output)
```

---

## 📁 Project Structure

```text
.
├── app.py                     # Gradio Web UI (In Progress)
├── main.py                    # CLI Entrypoint (Ready)
├── requirements.txt           # Project dependencies
├── .env.example               # Placeholder environment config
├── .gitignore                 # Git ignore rules
├── README.md                  # Project documentation
│
├── demo_bugs/                 # Sample bug demonstrations
│   └── bug1_off_by_one/
│
├── src/
│   ├── config.py              # Configuration constants
│   ├── graph.py               # LangGraph workflow orchestration (In Progress)
│   ├── llm.py                 # Multi-provider LLM interface (Groq/Gemini/OpenRouter/Ollama)
│   ├── state.py               # Shared DebugState contract
│   │
│   ├── agents/
│   │   ├── analyzer.py        # Member 1: Bug Analyzer Agent (Completed)
│   │   ├── test_generator.py  # Member 2: Pytest Test Generator (Completed)
│   │   └── fixer.py           # Member 3: Patch & Fixer Agent (In Progress)
│   │
│   ├── tools/
│   │   ├── code_parser.py     # Tree-sitter AST parser (Completed)
│   │   ├── test_runner.py     # Isolated Pytest runner with timeout (Completed)
│   │   └── git_pr.py          # GitHub PR automation tool (In Progress)
│   │
│   └── prompts/
│       ├── analyzer.md        # Analyzer system prompt & JSON schema
│       ├── test_generator.md  # Test Generator system prompt
│       └── fixer.md           # Fixer prompt template
│
└── tests/
    ├── test_analyzer.py       # Unit tests for Analyzer Agent
    └── test_code_parser.py    # Unit tests for Code Parser
```

---

## 📊 Development Status

### ✅ Completed
- **Analyzer Agent**: Full AST integration, root-cause diagnosis, coordinate snapping, retry analysis
- **Tree-sitter Code Parser**: Python AST parsing with native fallback, function extraction, boundary detection
- **Test Generator Agent**: Generates 3–5 reproducing pytest cases covering edge cases
- **Test Generator Prompt**: Structured prompt enforcing strict JSON output and valid Python syntax
- **Test Runner Tool**: Sandboxed temp directory execution, 20-second timeout safeguard, output capturing
- **LLM Provider Configuration**: Automatic priority and fallback across Groq, Gemini, OpenRouter, and Ollama
- **Analyzer → Test Generator → Test Runner Integration**: Validated on sample defects

### ⏳ In Progress
- **Fixer Agent**: Unified diff generation, surgical code patches
- **Git / PR Automation**: Branch creation, commit generation, and automated GitHub PR creation
- **LangGraph Workflow**: Cyclic graph routing with retry limits
- **Gradio UI**: Interactive web interface with real-time log streaming and diff viewer
- **End-to-End Pipeline**: Full autonomous loop from bug input to PR creation

---

## 🔒 Security Best Practices

- **API Keys**: Never commit `.env` or real API keys to GitHub.
- Use `.env` for real local credentials (ignored by git).
- Use `.env.example` only for placeholder configuration.
- If a secret is accidentally committed, revoke and rotate it immediately, and remove it from Git history.