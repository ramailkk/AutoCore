import requests

from util import fail

# Fast-tier provider. Swap/extend here if more providers get added later —
# callers only depend on chat(), not on how it's implemented.
GROQ_API = "https://api.groq.com/openai/v1/chat/completions"


def chat(system_prompt: str, user_prompt: str, api_key: str, model: str) -> str:
    resp = requests.post(
        GROQ_API,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "reasoning_format": "hidden",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        fail(f"LLM API call failed ({resp.status_code}): {resp.text[:500]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]
