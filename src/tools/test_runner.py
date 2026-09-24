import os
import sys
import subprocess
import tempfile


def run_tests(state) -> tuple[bool, str]:
    # Test fixed_code if Fixer has produced a repair, otherwise original source_code
    source_code = state.get("fixed_code") or state.get("source_code", "")
    generated_tests = state.get("generated_tests", "")
    file_path = state.get("file_path", "solution.py")

    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. Write source file at root of temp_dir (e.g. temp_dir/calculator.py)
        base_name = os.path.basename(file_path) if file_path else "solution.py"
        source_file = os.path.join(temp_dir, base_name)
        with open(source_file, "w", encoding="utf-8") as f:
            f.write(source_code)

        # 2. Also write source file at its full relative path (e.g. temp_dir/demo_bugs/bug1_off_by_one/calculator.py)
        # and create __init__.py files in every parent directory so relative package imports resolve
        if file_path:
            clean_rel = os.path.normpath(file_path).lstrip("/\\")
            nested_file = os.path.join(temp_dir, clean_rel)
            nested_dir = os.path.dirname(nested_file)
            if nested_dir and nested_dir != temp_dir:
                os.makedirs(nested_dir, exist_ok=True)
                curr = nested_dir
                while curr and curr != temp_dir and curr.startswith(temp_dir):
                    init_file = os.path.join(curr, "__init__.py")
                    if not os.path.exists(init_file):
                        with open(init_file, "w", encoding="utf-8") as f:
                            pass
                    curr = os.path.dirname(curr)
                with open(nested_file, "w", encoding="utf-8") as f:
                    f.write(source_code)

        # 3. Write test file
        test_file = os.path.join(temp_dir, "test_generated.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(generated_tests)

        # 4. Prepare environment with PYTHONPATH pointing to temp_dir
        env = os.environ.copy()
        current_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{temp_dir}{os.pathsep}{current_pp}" if current_pp else temp_dir

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                env=env,
                timeout=20
            )

            output = result.stdout + result.stderr
            return result.returncode == 0, output

        except subprocess.TimeoutExpired:
            return False, "Test execution timed out after 20 seconds."