from __future__ import annotations

import os
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import gradio as gr

try:
    from src.graph import build_graph
    GRAPH_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    GRAPH_IMPORT_ERROR = exc

    def build_graph() -> Any:
        raise RuntimeError("The backend graph could not be loaded. Check the agent modules and installed dependencies.") from GRAPH_IMPORT_ERROR


DEMO_SOURCE = "def add(a, b):\n    return a - b\n"
DEMO_ERROR = "AssertionError: assert add(2, 3) == 5"

THEME_JS = r"""
() => {
    const root = document.documentElement;
    const button = document.querySelector('.theme-toggle');
    const applyTheme = (theme) => {
        root.dataset.theme = theme;
        if (button) button.textContent = theme === 'light' ? 'DARK MODE' : 'LIGHT MODE';
        localStorage.setItem('debugflow-theme', theme);
    };
    applyTheme(localStorage.getItem('debugflow-theme') || 'dark');
    if (button && !button.dataset.bound) {
        button.dataset.bound = 'true';
        button.addEventListener('click', () => applyTheme(root.dataset.theme === 'light' ? 'dark' : 'light'));
    }
}
"""

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root { --ink:#f5f7fa; --muted:#9aa4b2; --bg:#05060a; --panel:rgba(255,255,255,.045); --line:rgba(255,255,255,.10); --field:rgba(0,0,0,.22); --terminal:#030407; --violet:#7c5cff; --cyan:#5ee7ff; --green:#45e6a5; --amber:#ffc857; --red:#ff5c7a; --shadow:rgba(0,0,0,.18); }
:root[data-theme="light"] { --ink:#172033; --muted:#596579; --bg:#eef3f8; --panel:rgba(255,255,255,.76); --line:rgba(23,32,51,.14); --field:rgba(255,255,255,.9); --terminal:#172033; --violet:#6043d6; --cyan:#087f9b; --green:#087d59; --amber:#936700; --red:#b52d4a; --shadow:rgba(32,49,76,.16); }
* { box-sizing:border-box; }
body, .gradio-container { margin:0 !important; background:var(--bg) !important; color:var(--ink) !important; font-family:'Space Grotesk',sans-serif !important; transition:background .35s ease,color .35s ease; }
.gradio-container, .gradio-container * { color-scheme:dark; }
:root[data-theme="light"] .gradio-container, :root[data-theme="light"] .gradio-container * { color-scheme:light; }
.gradio-container { max-width:1440px !important; padding:0 28px 64px !important; background-image:linear-gradient(rgba(125,145,170,.06) 1px, transparent 1px),linear-gradient(90deg,rgba(125,145,170,.06) 1px,transparent 1px),radial-gradient(circle at 18% 0%,rgba(124,92,255,.18),transparent 31%),radial-gradient(circle at 88% 28%,rgba(94,231,255,.10),transparent 27%); background-size:52px 52px,52px 52px,100% 100%,100% 100%; }
:root[data-theme="light"] .gradio-container { background-image:linear-gradient(rgba(85,108,134,.09) 1px, transparent 1px),linear-gradient(90deg,rgba(85,108,134,.09) 1px,transparent 1px),radial-gradient(circle at 15% 0%,rgba(124,92,255,.13),transparent 32%),radial-gradient(circle at 90% 20%,rgba(94,231,255,.14),transparent 28%); }
#topbar { border-bottom:1px solid var(--line); padding:20px 0 17px; margin-bottom:42px; display:flex; align-items:center; justify-content:space-between; gap:20px; }
.brand { display:flex; align-items:center; gap:11px; font-weight:600; font-size:18px; letter-spacing:-.02em; }
.brand-mark { width:25px; height:25px; display:grid; place-items:center; border:1px solid rgba(124,92,255,.7); border-radius:7px; background:linear-gradient(135deg,rgba(124,92,255,.9),rgba(94,231,255,.65)); color:#05060a; font-size:13px; font-weight:700; box-shadow:0 0 22px rgba(124,92,255,.3); }
.nav-meta { margin-left:auto; text-align:right; color:var(--muted); font:11px 'DM Mono',monospace; letter-spacing:.12em; text-transform:uppercase; }
.ready-dot { color:var(--green); }
.theme-toggle { flex:0 0 auto; min-width:112px; padding:8px 12px !important; color:var(--ink) !important; background:var(--panel) !important; border:1px solid var(--line) !important; border-radius:999px !important; font:10px 'DM Mono',monospace !important; letter-spacing:.08em; }
.hero { padding:12px 0 72px; display:grid; grid-template-columns:minmax(0,1fr) minmax(320px,430px); align-items:center; gap:48px; }
.hero-copy { max-width:850px; }
.eyebrow,.section-kicker { color:var(--cyan); font:500 11px 'DM Mono',monospace; letter-spacing:.18em; text-transform:uppercase; }
.hero h1 { font-size:clamp(48px,7vw,88px); line-height:.96; letter-spacing:-.075em; margin:18px 0 23px; max-width:760px; }
.hero h1 span { color:var(--muted); }
.hero p { max-width:620px; color:var(--muted); font-size:17px; line-height:1.65; margin:0; }
.hero-actions { margin-top:29px; }
.agent-visual { position:relative; min-height:390px; display:grid; place-items:center; isolation:isolate; }
.agent-visual:before { content:''; position:absolute; width:280px; height:280px; border-radius:50%; background:radial-gradient(circle,rgba(124,92,255,.25),transparent 68%); filter:blur(10px); z-index:-2; }
.agent-ring { position:absolute; width:310px; height:310px; border:1px solid rgba(94,231,255,.28); border-radius:50%; transform:rotateX(68deg) rotateZ(15deg); animation:orbit 10s linear infinite; box-shadow:0 0 35px rgba(94,231,255,.12); }
.agent-ring:after { content:''; position:absolute; left:12%; top:-5px; width:9px; height:9px; border-radius:50%; background:var(--cyan); box-shadow:0 0 18px var(--cyan); }
.agent-ring.two { width:245px; height:245px; transform:rotateY(68deg) rotateZ(-22deg); animation-duration:7s; animation-direction:reverse; border-color:rgba(124,92,255,.42); }
.agent-halo { position:absolute; width:190px; height:190px; border-radius:50%; border:1px solid rgba(255,255,255,.2); background:linear-gradient(135deg,rgba(255,255,255,.12),rgba(124,92,255,.08) 45%,rgba(94,231,255,.18)); box-shadow:inset -18px -20px 35px rgba(0,0,0,.4),0 0 45px rgba(94,231,255,.16); animation:float-agent 4.5s ease-in-out infinite; }
.agent-halo:before { content:''; position:absolute; inset:17px; border-radius:50%; border:1px dashed rgba(255,255,255,.34); animation:spin 12s linear infinite; }
.agent-face { position:absolute; width:106px; height:132px; border-radius:48% 52% 45% 45%; background:linear-gradient(145deg,#d9e5ee 0%,#718ca4 48%,#24384d 100%); box-shadow:inset -15px -12px 19px rgba(5,12,24,.42),0 18px 35px rgba(0,0,0,.35); transform:translateY(2px); }
.agent-face:before { content:''; position:absolute; left:20px; top:50px; width:66px; height:24px; border-radius:20px; background:#071321; box-shadow:0 0 16px rgba(94,231,255,.38); }
.agent-face:after { content:'•  •'; position:absolute; left:30px; top:48px; color:var(--cyan); font:18px 'DM Mono',monospace; letter-spacing:7px; text-shadow:0 0 10px var(--cyan); }
.agent-core-label { position:absolute; bottom:16px; color:var(--muted); font:10px 'DM Mono',monospace; letter-spacing:.18em; text-transform:uppercase; }
@keyframes orbit { to { transform:rotateX(68deg) rotateZ(375deg); } } @keyframes spin { to { transform:rotate(360deg); } } @keyframes float-agent { 50% { transform:translateY(-10px) scale(1.025); } }
.section { border-top:1px solid var(--line); padding:52px 0; }
.section-heading { display:flex; justify-content:space-between; gap:24px; align-items:flex-end; margin-bottom:24px; }
.section-heading h2 { margin:8px 0 0; font-size:30px; letter-spacing:-.05em; }
.section-heading p { color:var(--muted); margin:0; font-size:14px; }
.glass-panel { background:var(--panel); border:1px solid var(--line); border-radius:18px; box-shadow:0 16px 60px var(--shadow); }
.input-panel { padding:20px; }
label span { color:var(--muted) !important; font:11px 'DM Mono',monospace !important; letter-spacing:.12em; text-transform:uppercase; }
textarea, input, .gr-input, .gr-textbox { background:var(--field) !important; color:var(--ink) !important; border:1px solid var(--line) !important; border-radius:10px !important; }
textarea::placeholder, input::placeholder { color:var(--muted) !important; opacity:.9 !important; }
button, a, .gr-markdown, .prose, .tab-nav button, .tabs button { color:var(--ink) !important; }
.gr-markdown p, .gr-markdown li, .prose p, .prose li { color:var(--muted) !important; }
.gr-markdown a, .prose a { color:var(--cyan) !important; }
.tabs, .tabitem, .form, .block, .gr-box, .gr-panel, .gr-group { border-color:var(--line) !important; }
.tab-nav button.selected, .tab-nav button[aria-selected="true"] { color:var(--ink) !important; border-color:var(--violet) !important; }
.code-container, .cm-editor, .cm-scroller { background:var(--field) !important; color:var(--ink) !important; }
textarea:focus, input:focus { border-color:rgba(124,92,255,.8) !important; box-shadow:0 0 0 2px rgba(124,92,255,.15) !important; }
button { transition:transform .2s ease, border-color .2s ease, box-shadow .2s ease !important; }
button:hover { transform:translateY(-1px); }
.primary-button button { background:var(--violet) !important; color:white !important; border:0 !important; font-weight:600 !important; letter-spacing:.04em; box-shadow:0 8px 28px rgba(124,92,255,.28); }
.secondary-button button { background:transparent !important; color:var(--ink) !important; border:1px solid var(--line) !important; }
.upload-box { min-height:178px; border:1px dashed rgba(94,231,255,.36) !important; background:rgba(94,231,255,.025) !important; }
.upload-box:hover { border-color:var(--cyan) !important; }
.status-strip { min-height:48px; padding:14px 17px; border:1px solid var(--line); border-radius:11px; background:rgba(0,0,0,.24); font:12px 'DM Mono',monospace; color:var(--muted); }
.pipeline-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }
.agent-node { padding:17px; min-height:122px; border:1px solid var(--line); border-radius:14px; background:rgba(255,255,255,.03); position:relative; overflow:hidden; }
.agent-node:after { content:''; position:absolute; top:50%; right:-11px; width:10px; height:1px; background:rgba(255,255,255,.2); }
.agent-node:last-child:after { display:none; }
.agent-icon { font:15px 'DM Mono',monospace; color:var(--muted); }
.agent-name { margin-top:15px; font-size:13px; font-weight:600; letter-spacing:.03em; }
.agent-desc { margin-top:7px; color:var(--muted); font-size:12px; line-height:1.4; }
.agent-running { border-color:var(--violet); box-shadow:0 0 28px rgba(124,92,255,.22); animation:pulse 1.7s ease-in-out infinite; }
.agent-success { border-color:rgba(69,230,165,.55); }.agent-success .agent-icon { color:var(--green); }.agent-error { border-color:rgba(255,92,122,.65); }.agent-error .agent-icon { color:var(--red); }
@keyframes pulse { 50% { box-shadow:0 0 34px rgba(124,92,255,.38); } }
.terminal { background:var(--terminal) !important; border:1px solid var(--line) !important; border-radius:13px !important; font:12px/1.75 'DM Mono',monospace !important; color:#b9c4d2 !important; }
.log-wrap textarea { min-height:260px !important; }
.result-panel { padding:20px; min-height:270px; }
.result-panel pre, .result-panel code { font-family:'DM Mono',monospace !important; }
.empty-state { color:var(--muted); line-height:1.8; padding:20px 0; }
.about-panel { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(240px,.85fr); gap:32px; align-items:start; padding:26px; background:var(--panel); border:1px solid var(--line); border-radius:18px; box-shadow:0 16px 60px var(--shadow); }
.about-panel h3 { margin:7px 0 12px; font-size:25px; letter-spacing:-.04em; }
.about-panel p { color:var(--muted); line-height:1.7; margin:0; font-size:14px; }
.about-list { display:grid; gap:10px; margin:0; padding:0; list-style:none; }
.about-list li { color:var(--muted); border-left:2px solid var(--cyan); padding-left:13px; font:12px/1.5 'DM Mono',monospace; }
.success-state { color:var(--green); font:500 14px 'DM Mono',monospace; letter-spacing:.08em; }
.fail-state { color:var(--red); font:500 14px 'DM Mono',monospace; letter-spacing:.08em; }
.rights-line { color:var(--muted); text-align:center; font:11px 'DM Mono',monospace; padding-top:30px; letter-spacing:.08em; }
footer, .gradio-footer, .built-with, [data-testid="footer"] { display:none !important; }
@media(max-width:850px) { .gradio-container { padding:0 15px 40px !important; } #topbar { flex-wrap:wrap; } .nav-meta { order:3; width:100%; text-align:left; } .section-heading { display:block; } .section-heading p { margin-top:10px; } .pipeline-grid { grid-template-columns:1fr; } .agent-node:after { top:auto; right:50%; bottom:-11px; width:1px; height:10px; } .hero { grid-template-columns:1fr; padding-bottom:48px; gap:8px; } .hero h1 { font-size:54px; } .agent-visual { min-height:330px; transform:scale(.86); margin:-25px 0; } .about-panel { grid-template-columns:1fr; gap:22px; } }
@media(prefers-reduced-motion:reduce) { *,*:before,*:after { animation:none !important; transition:none !important; } }
"""


from src.tools.repo_loader import (
    safe_extract_zip,
    clone_or_download_repo,
    scan_workspace,
    detect_failing_tests,
    prepare_analyzer_payload,
    is_valid_github_url,
)


def upload_project(uploaded: str | None) -> tuple[str, Any, str, str, str, str]:
    if not uploaded:
        return "No project uploaded.", gr.update(choices=[], value=None), "", "", "", ""
    try:
        path = Path(uploaded)
        if path.suffix.lower() == ".zip":
            root, files = safe_extract_zip(str(path))
            if not files:
                return "No Python files detected in ZIP archive.", gr.update(choices=[], value=None), "", "", "", root
            
            # Automatically scan for failing tests in the extracted ZIP
            failing_file, detected_error = detect_failing_tests(root)
            selected_file = failing_file if failing_file else (files[0] if files else "solution.py")
            source_code = (Path(root) / selected_file).read_text(encoding="utf-8", errors="replace")
            
            test_tag = f" | ⚠️ Detected failing test in {Path(failing_file).name}" if failing_file else ""
            status_msg = f"✓ Extracted {path.name} ({len(files)} Python files){test_tag}"
            return status_msg, gr.update(choices=files, value=selected_file), selected_file, source_code, detected_error or "", root

        if path.suffix.lower() == ".py":
            source = path.read_text(encoding="utf-8", errors="replace")
            return f"✓ Loaded {path.name}", gr.update(choices=[path.name], value=path.name), path.name, source, "", str(path.parent)

        return "Please upload a .zip or .py file.", gr.update(choices=[], value=None), "", "", "", ""
    except Exception as exc:
        return f"Upload error: {exc}", gr.update(choices=[], value=None), "", "", "", ""


def load_github_repo(repo_url: str, branch: str) -> tuple[str, Any, str, str, str, str]:
    if not (repo_url or "").strip():
        return "Please enter a GitHub repository URL.", gr.update(choices=[], value=None, visible=False), "", "", "", ""
    if not is_valid_github_url(repo_url):
        return "Invalid GitHub URL. Expected format: https://github.com/owner/repository", gr.update(choices=[], value=None, visible=False), "", "", "", ""

    branch_name = (branch or "main").strip()
    try:
        cloned_dir, files = clone_or_download_repo(repo_url, branch_name)
        if not files:
            return f"Repository cloned, but no Python files were found on branch '{branch_name}'.", gr.update(choices=[], value=None, visible=False), "", "", "", cloned_dir

        # Auto-detect failing tests in the cloned repository
        failing_file, detected_error = detect_failing_tests(cloned_dir)
        selected_file = failing_file if failing_file else (files[0] if files else "solution.py")
        source_code = (Path(cloned_dir) / selected_file).read_text(encoding="utf-8", errors="replace")

        test_tag = f" | ⚠️ Auto-detected failing tests in {Path(failing_file).name}!" if failing_file else ""
        status_msg = f"✓ Cloned repository ({len(files)} Python files on branch '{branch_name}'){test_tag}"
        return status_msg, gr.update(choices=files, value=selected_file, visible=True), selected_file, source_code, detected_error or "", cloned_dir
    except Exception as exc:
        return f"Failed to clone repository: {exc}", gr.update(choices=[], value=None, visible=False), "", "", "", ""


def load_selected_file(choice: str | None, workspace: str | None) -> tuple[str, str]:
    if not choice or not workspace:
        return "", ""
    candidate = (Path(workspace) / choice).resolve()
    root = Path(workspace).resolve()
    if root not in candidate.parents or candidate.suffix.lower() != ".py":
        return choice or "", ""
    try:
        code = candidate.read_text(encoding="utf-8", errors="replace")
        return choice, code
    except OSError:
        return choice or "", ""


def load_demo() -> tuple[str, str, str]:
    return "calculator.py", DEMO_SOURCE, DEMO_ERROR


def pipeline_html(state: dict[str, Any], active: str = "") -> str:
    labels = [("01", "ANALYZER", "Root cause detection"), ("02", "TEST GENERATOR", "Reproduce failure"), ("03", "FIXER", "Candidate patch"), ("04", "VERIFY", "Run verification"), ("05", "PULL REQUEST", "Ready for review")]
    logs = " ".join(state.get("logs", [])).lower()
    error = state.get("test_passed") is False and state.get("attempts", 0) >= state.get("max_attempts", 3)
    html = ["<div class='pipeline-grid'>"]
    for number, name, desc in labels:
        key = name.split()[0].lower()
        if active == key:
            cls, icon = "agent-running", "◉"
        elif (name == "VERIFY" and state.get("test_passed") is True) or (name == "PULL REQUEST" and state.get("pr_url")) or key in logs:
            cls, icon = "agent-success", "✓"
        elif error and name == "VERIFY":
            cls, icon = "agent-error", "!"
        else:
            cls, icon = "", "○"
        html.append(f"<div class='agent-node {cls}'><div class='agent-icon'>{icon} {number}</div><div class='agent-name'>{name}</div><div class='agent-desc'>{desc}</div></div>")
    html.append("</div>")
    return "".join(html)


def format_analysis(analysis: Any) -> str:
    if not analysis:
        return "<div class='empty-state'>Analysis will appear here as the Analyzer agent inspects the failure.</div>"
    if isinstance(analysis, dict):
        rows = "".join(f"<p><b>{str(k).replace('_', ' ').upper()}</b><br>{v}</p>" for k, v in analysis.items())
        return f"<div class='result-panel'>{rows}</div>"
    return f"<div class='result-panel'>{analysis}</div>"


def format_pr_display(pr_url: Any) -> str:
    if not pr_url:
        return "The Pull Request link or local patch path will appear here once created."
    url_str = str(pr_url).strip()
    if url_str.startswith("http://") or url_str.startswith("https://"):
        return f"### 🎉 Pull Request Created!\n\n**PR Link:** [{url_str}]({url_str})\n\nBranch committed and ready for peer review on GitHub."
    return f"### 📁 Patch File Ready for Review!\n\n**Patch File:** `{url_str}`\n\nClick the download link below to download `fix.patch` directly to your computer, then apply it in your repository:\n```bash\ngit apply ~/Downloads/fix.patch\n```\n*(Or run `git apply output/fix.patch` if running locally in this repository)*"


def run_debugger(
    file_path: str,
    source_code: str,
    error_log: str,
    uploaded: str | None,
    target_file: str | None,
    repo_url: str,
    branch: str,
    workspace: str | None,
    repo_target_file: str | None,
    github_token: str | None = None,
) -> Iterator[tuple[Any, ...]]:
    repo_link = (repo_url or "").strip()
    active_file = repo_target_file if repo_link else (target_file if uploaded else file_path)
    no_patch = gr.update(visible=False)

    # 1. If GitHub URL is provided, clone and scan repository
    if repo_link:
        if not is_valid_github_url(repo_link):
            yield "<div class='fail-state'>! INVALID GITHUB URL</div>", pipeline_html({}, ""), "[system] Use a valid public https://github.com/owner/repository URL.", format_analysis(None), "", "", "", "", "", no_patch
            return
        try:
            if not workspace or not os.path.exists(workspace):
                cloned_dir, files = clone_or_download_repo(repo_link, branch.strip() or "main")
                workspace = cloned_dir
            payload = prepare_analyzer_payload(workspace, target_file=active_file, error_log=error_log)
            active_file = payload["file_path"]
            source_code = payload["source_code"]
            error_log = payload["error_log"]
        except Exception as exc:
            yield f"<div class='fail-state'>! REPOSITORY SCAN ERROR: {exc}</div>", pipeline_html({}, ""), f"[system] Failed to clone/scan repository: {exc}", format_analysis(None), "", "", "", "", "", no_patch
            return

    # 2. If uploaded project is provided, extract and scan ZIP
    elif uploaded:
        try:
            if not workspace or not os.path.exists(workspace):
                root, files = safe_extract_zip(uploaded)
                workspace = root
            payload = prepare_analyzer_payload(workspace, target_file=active_file, error_log=error_log)
            active_file = payload["file_path"]
            source_code = payload["source_code"]
            error_log = payload["error_log"]
        except Exception as exc:
            yield f"<div class='fail-state'>! ZIP EXTRACTION ERROR: {exc}</div>", pipeline_html({}, ""), f"[system] Failed to extract ZIP: {exc}", format_analysis(None), "", "", "", "", "", no_patch
            return

    if not source_code.strip():
        yield "<div class='fail-state'>! ADD SOURCE CODE BEFORE RUNNING</div>", pipeline_html({}, ""), "[system] Paste code, upload a project (.zip), or enter a GitHub repository URL.", format_analysis(None), "", "", "", "", "", no_patch
        return

    state: dict[str, Any] = {
        "repo_url": repo_link,
        "repo_path": workspace or "",
        "github_token": (github_token or "").strip(),
        "error_log": error_log or f"Automated defect inspection for {active_file}",
        "source_code": source_code,
        "file_path": active_file,
        "attempts": 0,
        "max_attempts": 3,
        "logs": [f"Analyzer: starting diagnosis on {active_file}" + (f" from {repo_link}" if repo_link else "")]
    }
    log_lines: list[str] = [
        "[system] DebugFlow AI initialized",
        f"[scanner] Loaded target file: {active_file}" + (f" from {repo_link}" if repo_link else ""),
        "[system] Streaming graph events through Analyzer -> Test Generator -> Fixer -> Verify..."
    ]
    yield "<div class='status-strip'>◉ DEBUGGING... agents are coordinating</div>", pipeline_html(state, "analyzer"), "\n".join(log_lines), format_analysis(None), "", "", "", "", "", no_patch
    try:
        for event in build_graph().stream(state):
            if isinstance(event, dict):
                # LangGraph stream yields {node_name: node_output}
                for node_name, node_output in event.items():
                    if isinstance(node_output, dict):
                        incoming_logs = node_output.get("logs", [])
                        previous_logs = state.get("logs", [])
                        state.update(node_output)

                        if incoming_logs:
                            state["logs"] = previous_logs + [str(item) for item in incoming_logs]
                            log_lines.extend(str(item) for item in incoming_logs[-3:])

                        if node_output.get("analysis"):
                            func_name = node_output["analysis"].get("function", "unknown")
                            log_lines.append(f"[agent] Analyzer identified root cause in '{func_name}'")
                        if node_output.get("generated_tests"):
                            log_lines.append("[agent] Test Generator synthesized reproduction tests")
                        if node_output.get("patch_diff"):
                            log_lines.append("[agent] Fixer generated unified patch diff")
                        if node_output.get("test_passed") is not None:
                            passed_flag = node_output["test_passed"]
                            log_lines.append("[verify] Verification PASSED! ✨" if passed_flag else f"[verify] Verification failed (attempt #{node_output.get('attempts', 1)}); retrying")
                        if node_output.get("pr_url"):
                            log_lines.append(f"[pr] Exported PR/Patch: {node_output.get('pr_url')}")

            active = "pull" if state.get("pr_url") else ("verify" if state.get("test_output") else ("fixer" if state.get("patch_diff") else ("test" if state.get("generated_tests") else "analyzer")))
            patch_file_avail = os.path.exists("output/fix.patch") and bool(state.get("patch_diff"))
            patch_update = gr.update(value="output/fix.patch", visible=True) if patch_file_avail else no_patch
            yield (
                "<div class='status-strip'>◉ DEBUGGING... live update received</div>",
                pipeline_html(state, active),
                "\n".join(log_lines[-80:]),
                format_analysis(state.get("analysis")),
                state.get("generated_tests", "") or "",
                state.get("fixed_code", "") or "",
                state.get("patch_diff", "") or "",
                state.get("test_output", "") or "",
                format_pr_display(state.get("pr_url")),
                patch_update,
            )

        passed = state.get("test_passed") is True
        final = "<div class='success-state'>✓ FIX VERIFIED · READY FOR REVIEW</div>" if passed else "<div class='fail-state'>! DEBUGGING STOPPED · MAXIMUM ATTEMPTS REACHED</div>"
        patch_file_avail = os.path.exists("output/fix.patch") and bool(state.get("patch_diff"))
        patch_update = gr.update(value="output/fix.patch", visible=True) if patch_file_avail else no_patch
        yield (
            final,
            pipeline_html(state, "pull" if passed else ""),
            "\n".join(log_lines[-80:]),
            format_analysis(state.get("analysis")),
            state.get("generated_tests", "") or "",
            state.get("fixed_code", "") or "",
            state.get("patch_diff", "") or "",
            state.get("test_output", "") or "",
            format_pr_display(state.get("pr_url")),
            patch_update,
        )
    except Exception as exc:
        details = f"[error] {type(exc).__name__}: {exc}"
        yield (
            "<div class='fail-state'>! SOMETHING WENT WRONG · SEE TECHNICAL DETAILS</div>",
            pipeline_html(state, ""),
            "\n".join(log_lines + [details]),
            format_analysis(state.get("analysis")),
            state.get("generated_tests", "") or "",
            state.get("fixed_code", "") or "",
            state.get("patch_diff", "") or "",
            state.get("test_output", "") or "",
            format_pr_display(state.get("pr_url")),
            no_patch,
        )



with gr.Blocks(title="DebugFlow AI") as demo:
    workspace = gr.State("")
    with gr.Row(elem_id="topbar"):
        gr.HTML("<div class='brand'><span class='brand-mark'>DF</span> DebugFlow AI</div>")
        gr.HTML("<div class='nav-meta'><span class='ready-dot'>●</span> SYSTEM READY &nbsp; / &nbsp; MULTI-AGENT DEBUGGER</div>")
        theme_switch = gr.Button("LIGHT MODE", elem_classes="theme-toggle", scale=0)
    gr.HTML("<section class='hero'><div class='hero-copy'><div class='eyebrow'>MULTI-AGENT CODE INTELLIGENCE</div><h1>Debug code.<br><span>Automatically.</span></h1><p>Analyze failures, generate reproduction tests, propose a fix, and verify the result before it reaches review.</p></div><div class='agent-visual' aria-label='Animated AI agent visualization'><div class='agent-ring'></div><div class='agent-ring two'></div><div class='agent-halo'></div><div class='agent-face'></div><div class='agent-core-label'>NEURAL CORE · ONLINE</div></div></section>")
    with gr.Row(elem_classes="hero-actions"):
        demo_button = gr.Button("Load Demo Bug", elem_classes="secondary-button", scale=0)
        jump_button = gr.Button("View Pipeline ↓", elem_classes="secondary-button", scale=0)

    with gr.Column(elem_classes="section"):
        gr.HTML("<div class='section-heading'><div><div class='section-kicker'>01 / INPUT</div><h2>Give the agents the failure context.</h2></div><p>Source stays local until the graph needs it.</p></div>")
        with gr.Tabs():
            with gr.Tab("Paste Code"):
                with gr.Row():
                    file_input = gr.Textbox(label="File path", value="calculator.py", scale=1)
                    error_input = gr.Textbox(label="Failing test / error log", placeholder="AssertionError: ...", scale=2)
                source_input = gr.Code(label="Source code", language="python", lines=12, value=DEMO_SOURCE)
            with gr.Tab("Upload Project"):
                with gr.Row():
                    upload = gr.File(label="UPLOAD PROJECT · .ZIP OR .PY", file_types=[".zip", ".py"], type="filepath", elem_classes="upload-box")
                    with gr.Column():
                        upload_status = gr.Markdown("No project uploaded. Upload a .zip or .py to auto-extract files.")
                        target_file = gr.Dropdown(label="Target Python file", choices=[], allow_custom_value=False)
                upload_error = gr.Markdown(visible=False)
            with gr.Tab("GitHub Repository"):
                with gr.Row():
                    repo_input = gr.Textbox(label="GitHub repository URL", placeholder="https://github.com/user/repository", scale=3)
                    branch_input = gr.Textbox(label="Branch", value="main", scale=1)
                    fetch_repo_btn = gr.Button("⚡ Fetch & Scan Repo", elem_classes="secondary-button", scale=1)
                with gr.Row():
                    github_token_input = gr.Textbox(label="GitHub Personal Access Token (Optional - to automatically open PR on GitHub)", placeholder="ghp_... (Leave blank to generate a downloadable patch)", type="password", scale=3)
                repo_status = gr.Markdown("Enter a public GitHub repository link (e.g. `https://github.com/owner/repo`) and click 'Fetch & Scan Repo'.")
                repo_target_file = gr.Dropdown(label="Discovered Repository Python Files", choices=[], allow_custom_value=False, visible=False)
        with gr.Row():
            run_button = gr.Button("▶  RUN DEBUGGER", elem_classes="primary-button", variant="primary", scale=2)
            clear_button = gr.ClearButton(value="Clear", components=[source_input, error_input, repo_input, github_token_input], elem_classes="secondary-button", scale=0)
        run_status = gr.HTML("<div class='status-strip'>READY TO DEBUG · Paste code, upload a project, or connect a repository.</div>")

    with gr.Column(elem_classes="section"):
        gr.HTML("<div class='section-heading'><div><div class='section-kicker'>02 / ORCHESTRATION</div><h2>Agent pipeline</h2></div><p>One graph. Multiple specialists. A verified outcome.</p></div>")
        pipeline = gr.HTML(pipeline_html({}))
        with gr.Row():
            log_output = gr.Textbox(label="LIVE AGENT ACTIVITY", value="[system] Awaiting a debugging run...", lines=10, interactive=False, elem_classes=["terminal", "log-wrap"], scale=2)
            retry_hint = gr.Markdown("**ATTEMPTS**\n\n`0 / 3`\n\nVerification failures route back to the Analyzer for another attempt.", elem_classes="glass-panel")

    with gr.Column(elem_classes="section"):
        gr.HTML("<div class='section-heading'><div><div class='section-kicker'>03 / RESULTS</div><h2>Evidence, not guesses.</h2></div><p>Every artifact stays visible for review.</p></div>")
        with gr.Tabs():
            with gr.Tab("Analysis"):
                analysis_output = gr.HTML(format_analysis(None))
            with gr.Tab("Generated Tests"):
                tests_output = gr.Code(label="Generated pytest", language="python", lines=12, interactive=False)
            with gr.Tab("Fixed Code"):
                fixed_output = gr.Code(label="Candidate fixed source", language="python", lines=12, interactive=False)
            with gr.Tab("Patch"):
                patch_output = gr.Textbox(label="PROPOSED PATCH", lines=12, interactive=False, elem_classes="terminal")
            with gr.Tab("Verification"):
                verification_output = gr.Textbox(label="Verification output", lines=10, interactive=False, elem_classes="terminal")
            with gr.Tab("Pull Request"):
                pr_output = gr.Markdown("The Pull Request link or local patch path will appear here when created.")
                download_patch = gr.File(label="📥 Download fix.patch", interactive=False, visible=False)
    with gr.Column(elem_classes="section"):
        gr.HTML("<div class='about-panel'><div><div class='section-kicker'>ABOUT DEBUGFLOW</div><h3>Autonomous debugging, with evidence at every step.</h3><p>DebugFlow AI coordinates specialized agents to inspect a failure, generate a reproduction, propose a patch, and verify the result before review. The interface keeps the reasoning trail, code artifacts, and verification output visible for a fast, trustworthy developer workflow.</p></div><ul class='about-list'><li>ANALYZE · locate the root cause</li><li>TEST · reproduce the failure</li><li>FIX · generate a reviewable patch</li><li>VERIFY · confirm the behavior</li></ul></div>")
    gr.HTML("<div class='rights-line'>DEBUGFLOW AI · AUTONOMOUS DEBUGGING FOR REAL-WORLD CODE · ALL RIGHTS RESERVED TO TEAMZEROIQ</div>")

    demo_button.click(load_demo, outputs=[file_input, source_input, error_input])
    upload.change(upload_project, inputs=upload, outputs=[upload_status, target_file, file_input, source_input, error_input, workspace])
    target_file.change(load_selected_file, inputs=[target_file, workspace], outputs=[file_input, source_input])
    fetch_repo_btn.click(load_github_repo, inputs=[repo_input, branch_input], outputs=[repo_status, repo_target_file, file_input, source_input, error_input, workspace])
    repo_target_file.change(load_selected_file, inputs=[repo_target_file, workspace], outputs=[file_input, source_input])
    run_button.click(
        run_debugger,
        inputs=[file_input, source_input, error_input, upload, target_file, repo_input, branch_input, workspace, repo_target_file, github_token_input],
        outputs=[run_status, pipeline, log_output, analysis_output, tests_output, fixed_output, patch_output, verification_output, pr_output, download_patch]
    )


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, show_error=False, js=THEME_JS, footer_links=[])
