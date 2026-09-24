"""
Repository and Project Loader Tool:
Extracts ZIP archives, clones/downloads GitHub repositories, scans Python source
and test files, and auto-detects failing tests to prepare inputs for the Analyzer agent.
"""

from __future__ import annotations

import os
import sys
import shutil
import tempfile
import zipfile
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from urllib.parse import urlparse
import urllib.request


def is_valid_github_url(url: str) -> bool:
    """Validate whether the URL points to a valid GitHub repository."""
    if not url or not isinstance(url, str):
        return False
    clean_url = url.strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc.lower() not in ("github.com", "www.github.com"):
        return False
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    return len(parts) >= 2


def parse_github_owner_repo(url: str) -> Tuple[str, str]:
    """Extract owner and repo name from GitHub URL."""
    clean_url = url.strip()
    parsed = urlparse(clean_url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {url}")
    owner = parts[0]
    repo = parts[1].replace(".git", "")
    return owner, repo


def safe_extract_zip(zip_path: str, target_dir: Optional[str] = None) -> Tuple[str, List[str]]:
    """
    Safely extract a ZIP archive avoiding path traversal / zip-slip vulnerabilities.
    Returns the extraction directory path and list of relative Python file paths.
    """
    extract_root = Path(target_dir or tempfile.mkdtemp(prefix="debugflow_zip_"))
    extract_root.mkdir(parents=True, exist_ok=True)
    resolved_root = extract_root.resolve()

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            # Security check: prevent zip-slip traversal
            target_path = (extract_root / member.filename).resolve()
            if resolved_root not in target_path.parents and target_path != resolved_root:
                raise ValueError(f"Unsafe path in ZIP archive: {member.filename}")
        archive.extractall(extract_root)

    # If the ZIP unpacked into a single top-level directory, adjust root
    children = [p for p in extract_root.iterdir() if p.name not in ("__MACOSX", ".DS_Store")]
    effective_root = extract_root
    if len(children) == 1 and children[0].is_dir():
        effective_root = children[0]

    python_files = [
        str(p.relative_to(effective_root))
        for p in effective_root.rglob("*.py")
        if p.is_file() and not p.name.startswith(".")
    ]
    return str(effective_root), sorted(python_files)


def clone_or_download_repo(repo_url: str, branch: str = "main") -> Tuple[str, List[str]]:
    """
    Clone or download a GitHub repository.
    Tries git clone first with shallow depth, falls back to downloading ZIP archive from GitHub.
    Returns (cloned_dir_path, list_of_python_files).
    """
    if not is_valid_github_url(repo_url):
        raise ValueError(f"Invalid GitHub URL: {repo_url}. Expected format: https://github.com/owner/repo")

    owner, repo = parse_github_owner_repo(repo_url)
    target_dir = tempfile.mkdtemp(prefix=f"debugflow_{repo}_")
    clean_url = f"https://github.com/{owner}/{repo}.git"

    # 1. Try shallow git clone
    try:
        cmd = ["git", "clone", "--depth", "1", "--branch", branch, clean_url, target_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            python_files = [
                str(p.relative_to(target_dir))
                for p in Path(target_dir).rglob("*.py")
                if p.is_file() and not p.name.startswith(".") and ".git" not in p.parts
            ]
            return target_dir, sorted(python_files)
    except Exception:
        # Fall back to zip download
        pass

    # 2. Fallback: Download repo zipball from GitHub
    archive_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
    zip_path = os.path.join(target_dir, f"{repo}.zip")
    try:
        req = urllib.request.Request(
            archive_url,
            headers={"User-Agent": "MultiAgent-Code-Debugger/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as response, open(zip_path, "wb") as out_file:
            shutil.copyfileobj(response, out_file)

        effective_dir, python_files = safe_extract_zip(zip_path, target_dir=os.path.join(target_dir, "extracted"))
        return effective_dir, python_files
    except Exception as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone or download repository from {repo_url} (branch: {branch}): {exc}")


def scan_workspace(workspace_path: str) -> Dict[str, Any]:
    """
    Scan a directory for Python source files, companion tests, and project metadata.
    """
    root = Path(workspace_path).resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Workspace path does not exist: {workspace_path}")

    all_py_files = [
        str(p.relative_to(root))
        for p in root.rglob("*.py")
        if p.is_file() and not p.name.startswith(".") and ".venv" not in p.parts and ".git" not in p.parts
    ]

    test_files = [f for f in all_py_files if Path(f).name.startswith("test_") or Path(f).name.endswith("_test.py")]
    source_files = [f for f in all_py_files if f not in test_files]

    return {
        "workspace": str(root),
        "total_files": len(all_py_files),
        "source_files": sorted(source_files),
        "test_files": sorted(test_files),
        "all_files": sorted(all_py_files),
    }


def detect_failing_tests(workspace_path: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str]]:
    """
    Run pytest on the workspace to detect if any existing tests fail.
    Returns (failing_file_candidate, error_log) or (None, None).
    """
    root = Path(workspace_path).resolve()
    scan = scan_workspace(str(root))
    if not scan["test_files"]:
        return None, None

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{root}:{env.get('PYTHONPATH', '')}"
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        output = (res.stdout + res.stderr).strip()

        if res.returncode != 0 and output:
            # Try to identify candidate source file from error output or scan
            candidate_file = None
            for src in scan["source_files"]:
                base = Path(src).stem
                if base in output:
                    candidate_file = src
                    break

            if not candidate_file and scan["source_files"]:
                candidate_file = scan["source_files"][0]

            return candidate_file, output

    except Exception:
        pass

    return None, None


def prepare_analyzer_payload(
    workspace_path: str,
    target_file: Optional[str] = None,
    error_log: Optional[str] = None
) -> Dict[str, Any]:
    """
    Prepare source code and error log payload ready for the Analyzer agent.
    """
    root = Path(workspace_path).resolve()
    scan = scan_workspace(str(root))

    selected_file = target_file
    detected_error = error_log

    if not detected_error or not selected_file:
        candidate_file, auto_error = detect_failing_tests(str(root))
        if not selected_file and candidate_file:
            selected_file = candidate_file
        if not detected_error and auto_error:
            detected_error = auto_error

    if not selected_file:
        if scan["source_files"]:
            selected_file = scan["source_files"][0]
        elif scan["all_files"]:
            selected_file = scan["all_files"][0]
        else:
            raise ValueError(f"No Python files found in workspace {workspace_path}")

    target_full_path = (root / selected_file).resolve()
    if not target_full_path.exists():
        raise FileNotFoundError(f"Target file not found: {selected_file}")

    source_code = target_full_path.read_text(encoding="utf-8", errors="replace")

    return {
        "workspace": str(root),
        "file_path": selected_file,
        "source_code": source_code,
        "error_log": detected_error or f"Test inspection initiated for {selected_file}",
        "all_files": scan["all_files"],
        "source_files": scan["source_files"],
        "test_files": scan["test_files"],
    }
