"""
Git and GitHub PR Tool:
Creates a remote branch, commits the fixed code, and opens a Pull Request via PyGithub.
Falls back to saving a unified diff patch to output/fix.patch if no GitHub token is provided.
"""

import os
import time
from typing import Dict, Any

from src.state import DebugState


def _save_local_patch(patch_diff: str, fixed_code: str, file_path: str) -> str:
    """Fallback handler: saves patch diff and fixed code to the output directory."""
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    patch_file_path = os.path.join(output_dir, "fix.patch")

    # If no patch_diff was provided, generate a fallback banner
    content_to_write = patch_diff
    if not content_to_write.strip():
        content_to_write = (
            f"# Automated patch for {file_path}\n"
            f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"{fixed_code}\n"
        )

    with open(patch_file_path, "w", encoding="utf-8") as f:
        f.write(content_to_write)

    # Also save the raw fixed file in output for easy inspection
    if fixed_code:
        base_name = os.path.basename(file_path) if file_path else "fixed_solution.py"
        fixed_file_path = os.path.join(output_dir, f"fixed_{base_name}")
        with open(fixed_file_path, "w", encoding="utf-8") as f:
            f.write(fixed_code)

    portable_patch_path = patch_file_path.replace(os.sep, "/")
    print(f"[git_pr] Local fallback: saved patch to {portable_patch_path}")
    return portable_patch_path


def open_pr(state: DebugState) -> str:
    """
    Open a Pull Request on GitHub with the repaired code, or save a local patch.

    Args:
        state: Shared DebugState dictionary.

    Returns:
        str: GitHub PR URL (e.g. 'https://github.com/.../pull/1') or
             local patch path ('output/fix.patch').
    """
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    repo_name = os.getenv("GITHUB_REPO")
    if not repo_name and state.get("repo_url"):
        from urllib.parse import urlparse
        parts = [p for p in urlparse(str(state["repo_url"]).strip()).path.strip("/").split("/") if p]
        if len(parts) >= 2:
            repo_name = f"{parts[0]}/{parts[1].replace('.git', '')}"
    file_path = state.get("file_path", "solution.py")
    fixed_code = state.get("fixed_code", "")
    patch_diff = state.get("patch_diff", "")
    analysis = state.get("analysis", {})

    # If no GitHub token, repository target, or verification explicitly failed, use local patch fallback
    if not token or not repo_name or state.get("test_passed") is False:
        return _save_local_patch(patch_diff, fixed_code, file_path)



    try:
        from github import Github
        gh = Github(token)
        repo = gh.get_repo(repo_name)

        # 1. Determine base branch
        base_branch = os.getenv("GITHUB_BASE_BRANCH") or repo.default_branch or "main"
        base_ref = repo.get_branch(base_branch)
        base_sha = base_ref.commit.sha

        # 2. Create unique fix branch
        function_name = analysis.get("function", "bugfix")
        branch_name = f"fix/{function_name}-{int(time.time())}"
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_sha)

        # 3. Update or create the repaired file on the new branch
        commit_message = f"fix({function_name}): automated patch from debugger agent"
        try:
            file_content = repo.get_contents(file_path, ref=branch_name)
            repo.update_file(
                path=file_path,
                message=commit_message,
                content=fixed_code,
                sha=file_content.sha,
                branch=branch_name,
            )
        except Exception:
            repo.create_file(
                path=file_path,
                message=commit_message,
                content=fixed_code,
                branch=branch_name,
            )

        # 4. Open GitHub Pull Request
        pr_title = f"fix({function_name}): resolve defect in {os.path.basename(file_path)}"
        root_cause = analysis.get("root_cause", "Automated bug repair.")
        pr_body = (
            f"## 🤖 Automated Bug Fix by Multi-Agent Debugger\n\n"
            f"### Root Cause Diagnosis\n{root_cause}\n\n"
            f"### Affected Function & Scope\n"
            f"- **File**: `{file_path}`\n"
            f"- **Function**: `{function_name}`\n"
            f"- **Line Range**: Lines {analysis.get('line_start', '?')} to {analysis.get('line_end', '?')}\n\n"
            f"### Unified Patch Diff\n"
            f"```diff\n{patch_diff}\n```\n"
        )

        pr = repo.create_pull(
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base=base_branch,
        )
        print(f"[git_pr] Successfully created Pull Request: {pr.html_url}")
        return pr.html_url

    except Exception as e:
        print(f"[git_pr] GitHub PR creation failed: {e}. Falling back to local patch.")
        return _save_local_patch(patch_diff, fixed_code, file_path)
