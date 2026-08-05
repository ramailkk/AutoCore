import os

from github_client import get_diff, post_comment
from llm_client import chat
from util import fail

MAX_DIFF_CHARS = 40_000
PROFILE_PATH = os.path.join(".reviewer", "profile.md")

SYSTEM_PROMPT = (
    "You are a concise code reviewer. You will be given a pull request diff, "
    "optionally preceded by a repo profile for context. "
    "Point out real bugs, risky changes, and clear style issues. "
    "Be specific (file/line if visible in the diff). "
    "If the diff looks fine, say so briefly. Do not pad the response."
)


def load_profile() -> str:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return f.read()
    return ""


def review_diff(diff: str, profile: str, api_key: str, model: str) -> str:
    truncated = diff[:MAX_DIFF_CHARS]
    note = "\n\n[diff truncated for length]" if len(diff) > MAX_DIFF_CHARS else ""

    user_prompt = ""
    if profile:
        user_prompt += f"# Repo profile\n\n{profile}\n\n# Diff to review\n\n"
    user_prompt += truncated + note

    return chat(SYSTEM_PROMPT, user_prompt, api_key, model)


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
    review = review_diff(diff, profile, api_key, model)
    post_comment(repo, pr_number, token, f"### AI Code Review\n\n{review}")
    print("Posted review comment.")


if __name__ == "__main__":
    main()
