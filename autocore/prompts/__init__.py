import os

_PROMPTS_DIR = os.path.dirname(__file__)


def load_prompt(name: str) -> str:
    path = os.path.join(_PROMPTS_DIR, f"{name}.md")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()
