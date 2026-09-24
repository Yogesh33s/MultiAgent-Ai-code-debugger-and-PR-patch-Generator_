import os
import json
import re


def _clean_json_string(text: str) -> str:
    """Strip markdown code fence blocks from text to extract raw JSON."""
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_llm(system: str, user: str) -> str:
    """
    Shared LLM call helper. Supports Anthropic, OpenAI, or a fallback mock mode.
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    # 1. Anthropic Claude (Primary default from spec)
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
            resp = client.messages.create(
                model=model,
                max_tokens=2000,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        except Exception as e:
            print(f"[llm] Anthropic call failed: {e}")

    # 2. OpenAI GPT
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            print(f"[llm] OpenAI call failed: {e}")

    # 3. Google Gemini
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=system)
            resp = model.generate_content(user)
            return resp.text
        except Exception as e:
            print(f"[llm] Gemini call failed: {e}")

    # 4. Fallback when no API keys are configured (for local testing / offline dev)
    print("[llm] NOTICE: No LLM API key configured (using local intelligent fallback).")
    
    # Extract file path if provided in prompt
    file_match = re.search(r"Target File:\s*([^\s\n]+)", user)
    target_file = file_match.group(1) if file_match else "unknown_file.py"
    
    # Extract traceback line like: file.py:452: in func_name
    tb_match = re.search(r":(\d+):\s+in\s+([a-zA-Z_][a-zA-Z0-9_]*)", user)
    if tb_match:
        line_num = int(tb_match.group(1))
        func_name = tb_match.group(2)
        start_line = max(1, line_num - 2)
        end_line = line_num + 2
    else:
        # Check if any known function name appears in the error log
        all_funcs = re.findall(r"- Function '([a-zA-Z_][a-zA-Z0-9_]*)' \(lines (\d+)-(\d+)\)", user)
        error_section = user
        if "--- Original Failing Test / Error Log ---" in user:
            error_section = user.split("--- Original Failing Test / Error Log ---")[1]
            if "--- Full Source Code ---" in error_section:
                error_section = error_section.split("--- Full Source Code ---")[0]

        detected_candidate = None
        for fname, fstart, fend in all_funcs:
            if fname in error_section and not fname.startswith("test_"):
                detected_candidate = (fname, int(fstart), int(fend))
                break

        if detected_candidate:
            func_name, start_line, end_line = detected_candidate
        elif all_funcs:
            func_name, start_line, end_line = all_funcs[0][0], int(all_funcs[0][1]), int(all_funcs[0][2])
        else:
            func_name = "unknown_function"
            start_line = 1
            end_line = 10

    return json.dumps({
        "root_cause": "Calculation or condition mismatch in function logic identified during test execution.",
        "file": target_file,
        "function": func_name,
        "line_start": start_line,
        "line_end": end_line
    })




def call_llm_json(system: str, user: str) -> dict:
    """
    Calls LLM and returns parsed JSON dictionary.
    Handles markdown code fence stripping and JSON errors gracefully.
    """
    text = call_llm(system + "\nReturn ONLY valid JSON, no markdown.", user)
    cleaned = _clean_json_string(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to locate first '{' and last '}'
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Failed to parse LLM response as JSON:\n{text}")
