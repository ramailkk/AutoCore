import json
import os

from github_client import get_diff, post_comment
from llm_client import chat
from util import fail

MAX_DIFF_CHARS = 40_000
PROFILE_PATH = os.path.join(".reviewer", "profile.md")
VALID_CATEGORIES = {"major", "minor", "advice", "none"}
LABELS = {
    "major": "Major",
    "minor": "Minor",
    "advice": "Advice",
    "none": "No issues found",
}

SYSTEM_PROMPT = (
    "You are a concise code reviewer. You will be given a pull request diff, "
    "optionally preceded by a repo profile for context. "
    "Point out real bugs, risky changes, and clear style issues. Be specific "
    "(file/line if visible in the diff).\n\n"
    "Respond with a single JSON object with exactly two fields: "
    '"category" and "review".\n'
    '"category" is one of:\n'
    '- "major": bugs, security issues, breaking changes, risky logic — needs '
    "human attention before merging.\n"
    '- "minor": safe, small, mechanical issues (formatting, typos, unused '
    "imports, dead code) — low risk.\n"
    '- "advice": non-blocking suggestions or style opinions, nothing actually '
    "wrong.\n"
    '- "none": the diff looks fine, nothing to flag.\n'
    '"review" is the review text — specific and unpadded, or a brief '
    'confirmation if category is "none".\n\n'
    "Output only the JSON object, nothing else — no markdown code fences, "
    "no commentary before or after it."
)


def load_profile() -> str:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return f.read()
    return ""


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def classify_diff(diff: str, profile: str, api_key: str, model: str) -> tuple[str, str]:
    truncated = diff[:MAX_DIFF_CHARS]
    note = "\n\n[diff truncated for length]" if len(diff) > MAX_DIFF_CHARS else ""

    user_prompt = ""
    if profile:
        user_prompt += f"# Repo profile\n\n{profile}\n\n# Diff to review\n\n"
    user_prompt += truncated + note

    raw = chat(SYSTEM_PROMPT, user_prompt, api_key, model)

    try:
        data = json.loads(strip_code_fence(raw))
        category = str(data.get("category", "")).lower()
        review = str(data.get("review", "")).strip()
        if category not in VALID_CATEGORIES or not review:
            raise ValueError("missing or invalid category/review field")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARNING: could not parse classification JSON ({e}); falling back to major/raw text")
        category = "major"
        review = raw

    return category, review


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN") or fail("GITHUB_TOKEN not set")
    api_key = os.environ.get("GROQ_API_KEY") or fail("GROQ_API_KEY not set")
    repo = os.environ.get("GITHUB_REPOSITORY") or fail("GITHUB_REPOSITORY not set")
    pr_number = os.environ.get("PR_NUMBER") or fail("PR_NUMBER not set")
    model = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")

    diff = get_diff(repo, pr_number, token)
    if not diff.strip():
        print("Empty diff, nothing to review.")
        return

    profile = load_profile()
    category, review = classify_diff(diff, profile, api_key, model)
    print(f"Classified as: {category}")

    label = LABELS.get(category, category)
    post_comment(repo, pr_number, token, f"### AI Code Review — {label}\n\n{review}")
    print("Posted review comment.")


if __name__ == "__main__":
    main()
