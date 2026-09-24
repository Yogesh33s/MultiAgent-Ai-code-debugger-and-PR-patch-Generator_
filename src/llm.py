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

    # Fail clearly if no LLM provider is configured
    raise RuntimeError(
        "No LLM API key configured or all LLM provider calls failed. "
        "Please set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY in your environment or .env file."
    )




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
