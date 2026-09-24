import os, json, time
from dotenv import load_dotenv
from openai import OpenAI   # pip install openai  (works for ALL providers below)
load_dotenv()

# Order = priority. Providers with no key in .env are skipped automatically.
# Model names change over time, so check each provider's model list if one errors.
PROVIDERS = [
    {"name": "groq",
     "base_url": "https://api.groq.com/openai/v1",
     "key_env": "GROQ_API_KEY",
     "model": "qwen/qwen3.8-27b",
     "fallback_models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]},
    {"name": "gemini",
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "key_env": "GEMINI_API_KEY",
     "model": "gemini-2.5-flash"},
    {"name": "openrouter",
     "base_url": "https://openrouter.ai/api/v1",
     "key_env": "OPENROUTER_API_KEY",
     "model": "meta-llama/llama-3.3-70b-instruct:free"},
    {"name": "ollama",                       # local, no key needed
     "base_url": "http://localhost:11434/v1",
     "key_env": None,
     "model": "qwen2.5-coder:7b"},
]

def _available():
    for p in PROVIDERS:
        if p["key_env"] is None:
            # only use ollama if you explicitly enable it
            if os.getenv("USE_OLLAMA") == "1":
                yield p, "ollama"
        elif os.getenv(p["key_env"]):
            yield p, os.getenv(p["key_env"])

def call_llm(system: str, user: str, retries: int = 2) -> str:
    last_err = None
    for provider, key in _available():
        client = OpenAI(base_url=provider["base_url"], api_key=key)
        candidate_models = [provider["model"]]
        if "fallback_models" in provider:
            for fm in provider["fallback_models"]:
                if fm not in candidate_models:
                    candidate_models.append(fm)

        for model in candidate_models:
            for attempt in range(retries):
                try:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": user}],
                        temperature=0.2,
                    )
                    content = resp.choices[0].message.content
                    if content and content.strip():
                        return content.strip()
                    # Check reasoning field if present on reasoning models
                    reasoning = getattr(resp.choices[0].message, "reasoning", None)
                    if reasoning and reasoning.strip():
                        return reasoning.strip()
                    print(f"[llm] {provider['name']} ({model}) returned empty content, retrying...")
                except Exception as e:          # rate limit, network, bad model name...
                    last_err = e
                    print(f"[llm] {provider['name']} ({model}) failed: {e}")
                    time.sleep(1 * (attempt + 1))   # wait, retry, then next provider/model
    raise RuntimeError(f"All LLM providers failed. Last error: {last_err}")

def _extract_json_dict(text: str) -> dict:
    import re
    if not text or not str(text).strip():
        raise ValueError("LLM returned empty response")

    cleaned = str(text).strip()
    # Strip markdown code blocks ```json ... ``` or ``` ... ```
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # 1. Try direct JSON parsing
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Extract outermost { ... }
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = cleaned[start:end + 1]
        try:
            data = json.loads(snippet)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # 3. Try strict=False for unescaped newlines/tabs inside strings
        try:
            data = json.loads(snippet, strict=False)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError(f"No JSON found in: {text[:200]}")

def call_llm_json(system: str, user: str) -> dict:
    text = call_llm(system + "\nReturn ONLY valid JSON. No markdown, no explanation.", user)
    return _extract_json_dict(text)

