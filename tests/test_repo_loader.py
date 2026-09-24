"""
Unit tests for repo_loader tool (src/tools/repo_loader.py).
Tests URL validation, safe zip extraction, workspace scanning, and payload preparation.
"""

import os
import zipfile
import tempfile
import pytest
from pathlib import Path

from src.tools.repo_loader import (
    is_valid_github_url,
    parse_github_owner_repo,
    safe_extract_zip,
    scan_workspace,
    detect_failing_tests,
    prepare_analyzer_payload,
)


def test_is_valid_github_url():
    assert is_valid_github_url("https://github.com/owner/repo") is True
    assert is_valid_github_url("https://github.com/owner/repo.git") is True
    assert is_valid_github_url("http://github.com/owner/repo") is True
    assert is_valid_github_url("https://notgithub.com/owner/repo") is False
    assert is_valid_github_url("https://github.com/onlyowner") is False
    assert is_valid_github_url("") is False
    assert is_valid_github_url(None) is False


def test_parse_github_owner_repo():
    owner, repo = parse_github_owner_repo("https://github.com/bhaveshk25/MultiAgent-Ai-code-debugger")
    assert owner == "bhaveshk25"
    assert repo == "MultiAgent-Ai-code-debugger"

    owner2, repo2 = parse_github_owner_repo("https://github.com/test-user/my-repo.git")
    assert owner2 == "test-user"
    assert repo2 == "my-repo"


def test_safe_extract_zip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, "test_project.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("calc.py", "def add(a, b): return a + b\n")
            zf.writestr("tests/test_calc.py", "from calc import add\ndef test_add(): assert add(1, 2) == 3\n")

        extracted_dir, py_files = safe_extract_zip(zip_path)
        assert os.path.exists(extracted_dir)
        assert any("calc.py" in f for f in py_files)
        assert any("test_calc.py" in f for f in py_files)


def test_scan_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        (Path(tmp_dir) / "app.py").write_text("print('hello')", encoding="utf-8")
        (Path(tmp_dir) / "test_app.py").write_text("def test_dummy(): pass", encoding="utf-8")

        scan = scan_workspace(tmp_dir)
        assert scan["total_files"] == 2
        assert "app.py" in scan["source_files"]
        assert "test_app.py" in scan["test_files"]


def test_detect_failing_tests_and_prepare_payload():
    with tempfile.TemporaryDirectory() as tmp_dir:
        source_code = "def subtract(a, b):\n    return a + b  # Bug\n"
        test_code = "from logic import subtract\ndef test_sub():\n    assert subtract(5, 2) == 3\n"

        (Path(tmp_dir) / "logic.py").write_text(source_code, encoding="utf-8")
        (Path(tmp_dir) / "test_logic.py").write_text(test_code, encoding="utf-8")

        failing_file, error_log = detect_failing_tests(tmp_dir)
        assert error_log is not None
        assert "assert 7 == 3" in error_log or "FAILED" in error_log

        payload = prepare_analyzer_payload(tmp_dir)
        assert payload["file_path"] in ("logic.py", "test_logic.py")
        assert "subtract" in payload["source_code"]
        assert payload["error_log"] is not None
