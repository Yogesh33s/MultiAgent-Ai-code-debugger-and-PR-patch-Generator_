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

THEME_INIT_JS = r"""
() => {
    function getSavedTheme() {
        const saved = localStorage.getItem('debugflow-theme') || localStorage.getItem('gradio-theme');
        if (saved === 'light' || saved === 'dark') return saved;
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark';
    }

    function applyTheme(theme) {
        const isDark = (theme === 'dark');
        const doc = document.documentElement;
        const body = document.body;

        if (isDark) {
            doc.classList.add('dark');
            body.classList.add('dark');
            doc.setAttribute('data-theme', 'dark');
        } else {
            doc.classList.remove('dark');
            body.classList.remove('dark');
            doc.setAttribute('data-theme', 'light');
        }

        try {
            localStorage.setItem('debugflow-theme', theme);
            localStorage.setItem('gradio-theme', theme);
        } catch (e) {}

        const btns = document.querySelectorAll('.theme-toggle');
        btns.forEach(b => {
            b.innerText = isDark ? '☀️ Light' : '🌙 Dark';
            b.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
        });
    }

    const initial = getSavedTheme();
    applyTheme(initial);

    const bindToggle = () => {
        const btns = document.querySelectorAll('.theme-toggle');
        btns.forEach(btn => {
            if (!btn.dataset.themeBound) {
                btn.dataset.themeBound = 'true';
                const isDark = document.documentElement.classList.contains('dark') || document.body.classList.contains('dark');
                btn.innerText = isDark ? '☀️ Light' : '🌙 Dark';
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const currentlyDark = document.documentElement.classList.contains('dark') || document.body.classList.contains('dark');
                    applyTheme(currentlyDark ? 'light' : 'dark');
                });
            }
        });
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindToggle);
    } else {
        bindToggle();
    }
    setTimeout(bindToggle, 300);
    setTimeout(bindToggle, 1000);
}
"""

TOGGLE_THEME_JS = r"""
() => {
    const doc = document.documentElement;
    const body = document.body;
    const isDark = doc.classList.contains('dark') || body.classList.contains('dark');
    const newTheme = isDark ? 'light' : 'dark';

    if (newTheme === 'dark') {
        doc.classList.add('dark');
        body.classList.add('dark');
        doc.setAttribute('data-theme', 'dark');
    } else {
        doc.classList.remove('dark');
        body.classList.remove('dark');
        doc.setAttribute('data-theme', 'light');
    }

    try {
        localStorage.setItem('debugflow-theme', newTheme);
        localStorage.setItem('gradio-theme', newTheme);
    } catch (e) {}

    const btns = document.querySelectorAll('.theme-toggle');
    btns.forEach(b => {
        b.innerText = newTheme === 'dark' ? '☀️ Light' : '🌙 Dark';
    });
}
"""

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
    --df-bg-page: #f8fafc;
    --df-bg-card: #ffffff;
    --df-bg-elevated: #f1f5f9;
    --df-border: #e2e8f0;
    --df-border-accent: rgba(124, 58, 237, 0.25);
    --df-border-active: #0284c7;
    --df-text-main: #0f172a;
    --df-text-secondary: #475569;
    --df-text-muted: #64748b;
    --df-primary: #7c3aed;
    --df-primary-hover: #6d28d9;
    --df-primary-soft: rgba(124, 58, 237, 0.08);
    --df-primary-glow: rgba(124, 58, 237, 0.2);
    --df-cyan: #0284c7;
    --df-emerald: #059669;
    --df-emerald-soft: rgba(5, 150, 105, 0.1);
    --df-rose: #e11d48;
    --df-rose-soft: rgba(225, 29, 72, 0.08);
    --df-terminal-bg: #090d16;
    --df-terminal-header: #0f172a;
    --df-terminal-text: #38bdf8;
    --df-card-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.06), 0 2px 6px -2px rgba(15, 23, 42, 0.04);
}

:root.dark, :root .dark, body.dark, [data-theme="dark"] {
    --df-bg-page: #07090e;
    --df-bg-card: #0f172a;
    --df-bg-elevated: #1e293b;
    --df-border: rgba(255, 255, 255, 0.09);
    --df-border-accent: rgba(139, 92, 246, 0.35);
    --df-border-active: rgba(6, 182, 212, 0.5);
    --df-text-main: #f8fafc;
    --df-text-secondary: #94a3b8;
    --df-text-muted: #64748b;
    --df-primary: #8b5cf6;
    --df-primary-hover: #a78bfa;
    --df-primary-soft: rgba(139, 92, 246, 0.12);
    --df-primary-glow: rgba(139, 92, 246, 0.35);
    --df-cyan: #06b6d4;
    --df-emerald: #10b981;
    --df-emerald-soft: rgba(16, 185, 129, 0.12);
    --df-rose: #f43f5e;
    --df-rose-soft: rgba(244, 63, 94, 0.12);
    --df-terminal-bg: #030712;
    --df-terminal-header: #0a0f1d;
    --df-terminal-text: #38bdf8;
    --df-card-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.35);
}

* { box-sizing: border-box; }

body {
    margin: 0 !important;
    background: var(--df-bg-page) !important;
    color: var(--df-text-main) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    transition: background 0.25s ease, color 0.25s ease;
}

.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
    padding: 0 24px 80px !important;
    background: var(--df-bg-page) !important;
    color: var(--df-text-main) !important;
}

/* TOPBAR */
#topbar {
    border-bottom: 1px solid var(--df-border);
    padding: 18px 0;
    margin-bottom: 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    font-weight: 700;
    font-size: 19px;
    letter-spacing: -0.02em;
    color: var(--df-text-main);
}
.brand-mark {
    width: 32px;
    height: 32px;
    display: grid;
    place-items: center;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--df-primary), #06b6d4);
    color: #ffffff;
    font-size: 15px;
    font-weight: 800;
    box-shadow: 0 2px 10px var(--df-primary-glow);
}
.nav-meta {
    display: flex;
    align-items: center;
    gap: 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.05em;
    color: var(--df-text-secondary);
}
.system-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 4px 11px;
    border-radius: 9999px;
    background: var(--df-emerald-soft);
    border: 1px solid rgba(16, 185, 129, 0.25);
    color: var(--df-emerald);
    font-weight: 600;
    font-size: 11px;
}
.pulse-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--df-emerald);
    box-shadow: 0 0 8px var(--df-emerald);
    animation: radar-pulse 2s infinite;
}
.theme-toggle {
    cursor: pointer;
    padding: 6px 14px !important;
    background: var(--df-bg-card) !important;
    border: 1px solid var(--df-border) !important;
    border-radius: 9999px !important;
    color: var(--df-text-main) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
    box-shadow: var(--df-card-shadow) !important;
}
.theme-toggle:hover {
    border-color: var(--df-primary) !important;
    transform: translateY(-1px);
}

/* HERO SECTION */
.hero {
    display: grid;
    grid-template-columns: 1.25fr 0.95fr;
    align-items: center;
    gap: 40px;
    padding: 12px 0 48px;
}
.hero-copy h1 {
    font-size: clamp(38px, 4.5vw, 56px);
    line-height: 1.08;
    letter-spacing: -0.04em;
    font-weight: 800;
    color: var(--df-text-main);
    margin: 14px 0 18px;
}
.hero-gradient {
    background: linear-gradient(135deg, #8b5cf6 0%, #06b6d4 50%, #10b981 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero-copy p {
    color: var(--df-text-secondary);
    font-size: 16px;
    line-height: 1.65;
    max-width: 600px;
    margin: 0;
}
.hero-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 24px;
}
.hero-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 6px;
    background: var(--df-bg-elevated);
    border: 1px solid var(--df-border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 500;
    color: var(--df-text-secondary);
}

/* HERO TELEMETRY DASHBOARD */
.hero-dashboard {
    background: var(--df-bg-card);
    border: 1px solid var(--df-border);
    border-radius: 14px;
    padding: 20px;
    box-shadow: var(--df-card-shadow);
}
.dashboard-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--df-border);
    margin-bottom: 14px;
}
.dash-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    color: var(--df-text-muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.dash-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    color: var(--df-emerald);
}
.swarm-flow-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.flow-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-radius: 8px;
    background: var(--df-bg-elevated);
    border: 1px solid var(--df-border);
    font-size: 12px;
}
.flow-item-left {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: var(--df-text-main);
}
.flow-item-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--df-text-muted);
}
.dashboard-metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px solid var(--df-border);
}
.metric-box {
    text-align: center;
    padding: 6px 4px;
}
.metric-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 700;
    color: var(--df-primary);
}
.metric-lbl {
    font-size: 10px;
    color: var(--df-text-muted);
    margin-top: 2px;
}

/* SECTION HEADINGS */
.section {
    border-top: 1px solid var(--df-border);
    padding: 40px 0 20px;
}
.section-kicker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    color: var(--df-cyan);
    letter-spacing: 0.12em;
    text-transform: uppercase;
}
.section-heading {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 20px;
}
.section-heading h2 {
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: var(--df-text-main);
    margin: 4px 0 0;
}
.section-heading p {
    color: var(--df-text-secondary);
    margin: 0;
    font-size: 13px;
}

/* BUTTONS */
.primary-button button {
    background: linear-gradient(135deg, var(--df-primary), #6366f1) !important;
    color: #ffffff !important;
    border: 0 !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    letter-spacing: 0.04em !important;
    padding: 11px 24px !important;
    box-shadow: 0 4px 15px var(--df-primary-glow) !important;
    transition: all 0.2s ease !important;
}
.primary-button button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px var(--df-primary-glow) !important;
}
.secondary-button button {
    background: var(--df-bg-card) !important;
    border: 1px solid var(--df-border) !important;
    border-radius: 8px !important;
    color: var(--df-text-main) !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    transition: all 0.2s ease !important;
}
.secondary-button button:hover {
    border-color: var(--df-border-accent) !important;
    background: var(--df-bg-elevated) !important;
    transform: translateY(-1px);
}

/* PIPELINE GRID */
.pipeline-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-bottom: 18px;
}
.agent-node {
    padding: 14px 14px;
    min-height: 116px;
    border: 1px solid var(--df-border);
    border-radius: 12px;
    background: var(--df-bg-card);
    box-shadow: var(--df-card-shadow);
    transition: all 0.3s ease;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.agent-icon {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    color: var(--df-text-muted);
}
.agent-name {
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.04em;
    color: var(--df-text-main);
    margin-top: 8px;
}
.agent-desc {
    color: var(--df-text-secondary);
    font-size: 11px;
    line-height: 1.35;
    margin-top: 3px;
}
.agent-running {
    border-color: var(--df-primary) !important;
    background: var(--df-primary-soft) !important;
    box-shadow: 0 0 20px var(--df-primary-glow) !important;
    animation: active-pulse 2s infinite alternate;
}
.agent-running .agent-name {
    color: var(--df-primary);
}
.agent-success {
    border-color: rgba(16, 185, 129, 0.45) !important;
    background: var(--df-emerald-soft) !important;
}
.agent-success .agent-name {
    color: var(--df-emerald);
}
.agent-error {
    border-color: rgba(244, 63, 94, 0.5) !important;
    background: var(--df-rose-soft) !important;
}
.agent-error .agent-name {
    color: var(--df-rose);
}

/* TERMINAL CHROME */
.terminal-window {
    background: var(--df-terminal-bg);
    border: 1px solid var(--df-border);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: var(--df-card-shadow);
}
.terminal-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    background: var(--df-terminal-header);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.mac-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
}
.dot-red { background: #ff5f56; }
.dot-yellow { background: #ffbd2e; }
.dot-green { background: #27c93f; }
.terminal-title {
    margin-left: auto;
    margin-right: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #94a3b8;
}
.terminal textarea {
    background: var(--df-terminal-bg) !important;
    border: 0 !important;
    box-shadow: none !important;
    color: var(--df-terminal-text) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    line-height: 1.65 !important;
}

/* STATUS STRIP */
.status-strip {
    padding: 12px 18px;
    border: 1px solid var(--df-border);
    border-radius: 10px;
    background: var(--df-bg-elevated);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--df-text-secondary);
    display: flex;
    align-items: center;
    gap: 8px;
}
.success-state {
    padding: 12px 18px;
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 10px;
    background: var(--df-emerald-soft);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--df-emerald);
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
}
.fail-state {
    padding: 12px 18px;
    border: 1px solid rgba(244, 63, 94, 0.35);
    border-radius: 10px;
    background: var(--df-rose-soft);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--df-rose);
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* RESULTS & STATS */
.result-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
}
.result-stat-box {
    padding: 14px 16px;
    border-radius: 10px;
    background: var(--df-bg-elevated);
    border: 1px solid var(--df-border);
}
.stat-box-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    text-transform: uppercase;
    color: var(--df-cyan);
    font-weight: 700;
    letter-spacing: 0.08em;
}
.stat-box-value {
    font-size: 14px;
    font-weight: 600;
    margin-top: 4px;
    color: var(--df-text-main);
}
.diagnosis-box {
    padding: 16px;
    border-radius: 10px;
    background: var(--df-primary-soft);
    border: 1px solid var(--df-border-accent);
    margin-top: 10px;
}

/* ABOUT PANEL */
.about-panel {
    display: grid;
    grid-template-columns: 1.2fr 0.8fr;
    gap: 24px;
    padding: 24px;
    border-radius: 12px;
    background: var(--df-bg-elevated);
    border: 1px solid var(--df-border);
}
.about-panel h3 {
    margin: 8px 0 10px;
    font-size: 17px;
    color: var(--df-text-main);
    font-weight: 700;
}
.about-panel p {
    color: var(--df-text-secondary);
    font-size: 13px;
    line-height: 1.6;
    margin: 0;
}
.about-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--df-text-secondary);
}
.about-list li {
    padding: 8px 12px;
    background: var(--df-bg-card);
    border: 1px solid var(--df-border);
    border-radius: 6px;
}

/* RIGHTS */
.rights-line {
    text-align: center;
    color: var(--df-text-muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    padding-top: 32px;
}
footer, .gradio-footer, .built-with, [data-testid="footer"] { display: none !important; }

@keyframes radar-pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
    70% { transform: scale(1); box-shadow: 0 0 0 7px rgba(16, 185, 129, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}
@keyframes active-pulse {
    0% { box-shadow: 0 0 10px rgba(139, 92, 246, 0.2); }
    100% { box-shadow: 0 0 25px rgba(139, 92, 246, 0.5); }
}

@media(max-width: 900px) {
    .hero { grid-template-columns: 1fr; gap: 24px; }
    .about-panel { grid-template-columns: 1fr; }
    .pipeline-grid { grid-template-columns: 1fr; }
    .hero h1 { font-size: 34px; }
}
"""

theme = gr.themes.Soft(
    primary_hue="violet",
    secondary_hue="cyan",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "-apple-system", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
)

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
    steps = [
        ("01", "ANALYZER", "Root cause detection", "🔍"),
        ("02", "TEST GENERATOR", "Reproduce failure", "🧪"),
        ("03", "FIXER", "Candidate patch", "🛠️"),
        ("04", "VERIFY", "Isolated pytest", "⚡"),
        ("05", "PULL REQUEST", "Export PR / patch", "🚀"),
    ]
    logs = " ".join(state.get("logs", [])).lower()
    error = state.get("test_passed") is False and state.get("attempts", 0) >= state.get("max_attempts", 3)
    html = ["<div class='pipeline-grid'>"]
    for number, name, desc, emoji in steps:
        key = name.split()[0].lower()
        if active == key:
            cls = "agent-running"
            badge = "◉ ACTIVE"
        elif (name == "VERIFY" and state.get("test_passed") is True) or (name == "PULL REQUEST" and state.get("pr_url")) or key in logs:
            cls = "agent-success"
            badge = "✓ PASSED"
        elif error and name == "VERIFY":
            cls = "agent-error"
            badge = "! FAILED"
        else:
            cls = ""
            badge = f"○ {number}"
        html.append(f"""
        <div class='agent-node {cls}'>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class='agent-icon'>{emoji}</span>
                <span style="font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:700; opacity:0.85;">{badge}</span>
            </div>
            <div>
                <div class='agent-name'>{name}</div>
                <div class='agent-desc'>{desc}</div>
            </div>
        </div>
        """)
    html.append("</div>")
    return "".join(html)


def format_analysis(analysis: Any) -> str:
    if not analysis:
        return "<div class='empty-state' style='padding:24px; color:var(--df-text-muted); font-family:\"JetBrains Mono\",monospace;'>○ Awaiting Analyzer agent diagnosis... Click 'Run Debugger' to inspect defects.</div>"
    if isinstance(analysis, dict):
        fn = analysis.get("function", "module")
        file_name = analysis.get("file", "unknown")
        lines = f"{analysis.get('line_start', '?')} - {analysis.get('line_end', '?')}"
        root_cause = analysis.get("root_cause", "Defect identified in source code.")

        return f"""
        <div class="result-card-grid">
            <div class="result-stat-box">
                <div class="stat-box-label">🎯 Targeted Function</div>
                <div class="stat-box-value"><code>{fn}</code></div>
            </div>
            <div class="result-stat-box">
                <div class="stat-box-label">📁 File Path</div>
                <div class="stat-box-value"><code>{file_name}</code></div>
            </div>
            <div class="result-stat-box">
                <div class="stat-box-label">📍 Line Coordinates</div>
                <div class="stat-box-value"><code>Lines {lines}</code></div>
            </div>
        </div>
        <div class="diagnosis-box">
            <div class="stat-box-label" style="color:var(--df-primary); margin-bottom:8px;">🔍 Root Cause Diagnosis</div>
            <div style="font-size:14px; line-height:1.65; color:var(--df-text-main);">{root_cause}</div>
        </div>
        """
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


HEAD_HTML = r"""
<script>
(() => {
    try {
        const saved = localStorage.getItem('debugflow-theme') || localStorage.getItem('gradio-theme');
        const theme = (saved === 'light' || saved === 'dark') ? saved :
            ((window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark');
        const isDark = (theme === 'dark');
        const doc = document.documentElement;
        const body = document.body;
        if (isDark) {
            doc.classList.add('dark');
            if (body) body.classList.add('dark');
            doc.setAttribute('data-theme', 'dark');
        } else {
            doc.classList.remove('dark');
            if (body) body.classList.remove('dark');
            doc.setAttribute('data-theme', 'light');
        }
    } catch (e) {}
})();
</script>
"""

with gr.Blocks(title="DebugFlow AI") as demo:
    workspace = gr.State("")

    with gr.Row(elem_id="topbar"):
        gr.HTML("""
        <div class='brand'>
            <span class='brand-mark'>⚡</span>
            <span>DebugFlow<span style="color:var(--df-primary); font-weight:800;">.ai</span></span>
        </div>
        """)
        gr.HTML("""
        <div class='nav-meta'>
            <div class='system-badge'>
                <div class='pulse-dot'></div>
                <span>SWARM OPERATIONAL</span>
            </div>
            <span>LANGGRAPH · TREE-SITTER</span>
        </div>
        """)
        theme_switch = gr.Button("☀️ Light", elem_classes="theme-toggle", scale=0)

    gr.HTML("""
    <section class='hero'>
        <div class='hero-copy'>
            <div class='section-kicker'>⚡ AUTONOMOUS MULTI-AGENT INTELLIGENCE</div>
            <h1>Autonomous Code Repair.<br><span class='hero-gradient'>Verified in Sandbox.</span></h1>
            <p>An orchestrated swarm of specialized AI agents that parses syntax trees with Tree-sitter, isolates defects, generates reproducing pytest suites, applies minimal repairs, and delivers verified PR patches.</p>
            <div class='hero-badges'>
                <div class='hero-chip'><span>🔍</span> Tree-sitter AST</div>
                <div class='hero-chip'><span>🧪</span> Automated Reproduction</div>
                <div class='hero-chip'><span>⚡</span> Isolated Verification</div>
                <div class='hero-chip'><span>🚀</span> 1-Click PR / Patch</div>
            </div>
        </div>
        <div class='hero-dashboard'>
            <div class='dashboard-header'>
                <span class='dash-title'>Swarm Architecture & Telemetry</span>
                <span class='dash-status'><span class='pulse-dot'></span> ONLINE</span>
            </div>
            <div class='swarm-flow-list'>
                <div class='flow-item'>
                    <div class='flow-item-left'><span>🔍</span> 01 Analyzer Agent</div>
                    <span class='flow-item-badge'>AST Boundary Snapping</span>
                </div>
                <div class='flow-item'>
                    <div class='flow-item-left'><span>🧪</span> 02 Test Generator</div>
                    <span class='flow-item-badge'>Targeted Pytest Suite</span>
                </div>
                <div class='flow-item'>
                    <div class='flow-item-left'><span>🛠️</span> 03 Fixer Agent</div>
                    <span class='flow-item-badge'>Unified Diff Patch</span>
                </div>
                <div class='flow-item'>
                    <div class='flow-item-left'><span>⚡</span> 04 Verifier Node</div>
                    <span class='flow-item-badge'>Isolated Pytest Sandbox</span>
                </div>
                <div class='flow-item'>
                    <div class='flow-item-left'><span>🚀</span> 05 Dispatcher Node</div>
                    <span class='flow-item-badge'>GitHub PR / fix.patch</span>
                </div>
            </div>
            <div class='dashboard-metrics'>
                <div class='metric-box'>
                    <div class='metric-num'>100%</div>
                    <div class='metric-lbl'>Sandbox Isolation</div>
                </div>
                <div class='metric-box'>
                    <div class='metric-num'>3 Loops</div>
                    <div class='metric-lbl'>Retry Budget</div>
                </div>
                <div class='metric-box'>
                    <div class='metric-num'>Python 3.10+</div>
                    <div class='metric-lbl'>Runtime Target</div>
                </div>
            </div>
        </div>
    </section>
    """)
    with gr.Row(elem_classes="hero-actions"):
        demo_button = gr.Button("✨ Load Demo Bug", elem_classes="secondary-button", scale=0)
        jump_button = gr.Button("Explore Swarm Pipeline ↓", elem_classes="secondary-button", scale=0)

    with gr.Column(elem_classes="section"):
        gr.HTML("<div class='section-heading'><div><div class='section-kicker'>01 / INGESTION</div><h2>Defect Context & Source Code</h2></div><p>Source code remains isolated in an ephemeral sandbox.</p></div>")
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

    with gr.Column(elem_id="pipeline-section", elem_classes="section"):
        gr.HTML("<div class='section-heading'><div><div class='section-kicker'>02 / ORCHESTRATION</div><h2>Agent Swarm Pipeline</h2></div><p>Cyclical LangGraph state machine with automatic isolated verification.</p></div>")
        pipeline = gr.HTML(pipeline_html({}))
        with gr.Row():
            with gr.Column(scale=3):
                gr.HTML("""
                <div class='terminal-window'>
                    <div class='terminal-header'>
                        <div class='mac-dot dot-red'></div>
                        <div class='mac-dot dot-yellow'></div>
                        <div class='mac-dot dot-green'></div>
                        <div class='terminal-title'>debugflow-agent-swarm.log · live trace</div>
                    </div>
                </div>
                """)
                log_output = gr.Textbox(label="LIVE AGENT ACTIVITY", value="[system] Awaiting a debugging run...", lines=10, interactive=False, elem_classes=["terminal", "log-wrap"], show_label=False)
            with gr.Column(scale=1):
                retry_hint = gr.Markdown("**DEBUG BUDGET**\n\n`Max 3 Attempts`\n\nIf verification tests fail, the runtime feeds the pytest failure trace back into the Analyzer to re-evaluate the diagnosis.", elem_classes="glass-panel")

    with gr.Column(elem_classes="section"):
        gr.HTML("<div class='section-heading'><div><div class='section-kicker'>03 / RESULTS</div><h2>Verified Repair Artifacts</h2></div><p>Every diagnostic artifact and diff stays visible for review.</p></div>")
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

    # Wire event handlers
    demo_button.click(load_demo, outputs=[file_input, source_input, error_input])
    jump_button.click(fn=None, js="() => { const el = document.getElementById('pipeline-section'); if (el) el.scrollIntoView({ behavior: 'smooth' }); }")
    theme_switch.click(fn=None, js=TOGGLE_THEME_JS)
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
    port = int(os.getenv("PORT", 7860))
    share_live = os.getenv("SHARE", "true").lower() in ("true", "1", "yes")
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=False,
        theme=theme,
        css=CSS,
        js=THEME_INIT_JS,
        head=HEAD_HTML,
        share=share_live,
        footer_links=[],
    )
