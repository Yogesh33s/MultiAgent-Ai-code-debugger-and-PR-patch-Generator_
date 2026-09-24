"""
Unit tests for Member 3 - Git & PR Tool (src/tools/git_pr.py).
Tests local patch file saving, PyGithub PR creation, and API error fallbacks.
"""

import os
import shutil
import pytest
from unittest.mock import patch, MagicMock

from src.state import DebugState
from src.tools import git_pr


@pytest.fixture(autouse=True)
def cleanup_output_dir():
    """Ensure output directory is cleaned up before and after tests."""
    yield
    if os.path.exists("output"):
        shutil.rmtree("output", ignore_errors=True)


def test_open_pr_fallback_when_no_token():
    """Verify open_pr saves output/fix.patch when no GITHUB_TOKEN is configured."""
    diff_text = """--- a/calculator.py
+++ b/calculator.py
@@ -1,3 +1,3 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
    state: DebugState = {
        "file_path": "calculator.py",
        "fixed_code": "def add(a, b):\n    return a + b\n",
        "patch_diff": diff_text,
        "analysis": {"function": "add", "root_cause": "Operator discrepancy"},
    }

    # Ensure no token in environment
    with patch.dict(os.environ, {}, clear=True):
        result_path = git_pr.open_pr(state)

    assert result_path == "output/fix.patch"
    assert os.path.exists("output/fix.patch")
    with open("output/fix.patch", "r", encoding="utf-8") as f:
        saved_content = f.read()
    assert "-    return a - b" in saved_content
    assert "+    return a + b" in saved_content

    # Also verify fixed file saved
    assert os.path.exists("output/fixed_calculator.py")


def test_open_pr_with_mocked_pygithub():
    """Verify open_pr creates a GitHub ref and pull request when token is provided."""
    state: DebugState = {
        "file_path": "calculator.py",
        "fixed_code": "def add(a, b):\n    return a + b\n",
        "patch_diff": "diff --git a/calculator.py b/calculator.py",
        "analysis": {"function": "add", "root_cause": "Fixed addition operator"},
    }

    mock_pr = MagicMock()
    mock_pr.html_url = "https://github.com/org/repo/pull/42"

    mock_repo = MagicMock()
    mock_repo.default_branch = "main"
    mock_repo.get_branch.return_value.commit.sha = "base_commit_sha"
    mock_repo.create_pull.return_value = mock_pr

    mock_github = MagicMock()
    mock_github.get_repo.return_value = mock_repo

    env_vars = {
        "GITHUB_TOKEN": "ghp_fake_test_token",
        "GITHUB_REPO": "testorg/testrepo",
    }

    with patch.dict(os.environ, env_vars), \
         patch("github.Github", return_value=mock_github):
        pr_url = git_pr.open_pr(state)

    assert pr_url == "https://github.com/org/repo/pull/42"
    mock_github.get_repo.assert_called_once_with("testorg/testrepo")
    mock_repo.create_git_ref.assert_called_once()
    mock_repo.create_pull.assert_called_once()


def test_open_pr_api_failure_falls_back_to_patch():
    """Verify that an API error during PyGithub calls gracefully falls back to output/fix.patch."""
    state: DebugState = {
        "file_path": "calculator.py",
        "fixed_code": "def add(a, b):\n    return a + b\n",
        "patch_diff": "sample diff",
        "analysis": {"function": "add"},
    }

    env_vars = {
        "GITHUB_TOKEN": "ghp_fake_test_token",
        "GITHUB_REPO": "testorg/testrepo",
    }

    with patch.dict(os.environ, env_vars), \
         patch("github.Github", side_effect=Exception("GitHub API 401 Unauthorized")):
        result_path = git_pr.open_pr(state)

    assert result_path == "output/fix.patch"
    assert os.path.exists("output/fix.patch")
