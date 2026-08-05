import requests

from util import fail

# Provider endpoints. Both are OpenAI-compatible chat-completions APIs, so
# one chat() function covers both — callers pick a provider by name rather
# than depending on how each is implemented.
PROVIDER_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}


def chat(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    provider: str = "groq",
) -> str:
    url = PROVIDER_ENDPOINTS[provider]
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    if provider == "groq":
        # Groq-specific: strips reasoning-model thinking traces from output.
        # Not a standard OpenAI-compatible param — scoped to Groq only.
        body["reasoning_format"] = "hidden"

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json=body,
        timeout=60,
    )
    if resp.status_code != 200:
        fail(f"{provider} API call failed ({resp.status_code}): {resp.text[:500]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]
