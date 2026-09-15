import requests

from autocore.config import load_config
from autocore.util import fail


def chat(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str,
    provider: str = "groq",
) -> str:
    url = load_config()[provider]["api_url"]
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
