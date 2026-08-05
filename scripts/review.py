import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_API = "https://api.github.com"
GROQ_API = "https://api.groq.com/openai/v1/chat/completions"
MAX_DIFF_CHARS = 40_000

SYSTEM_PROMPT = (
    "You are a concise code reviewer. You will be given a pull request diff. "
    "Point out real bugs, risky changes, and clear style issues. "
    "Be specific (file/line if visible in the diff). "
    "If the diff looks fine, say so briefly. Do not pad the response."
)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def get_diff(repo: str, pr_number: str, token: str) -> str:
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        fail(f"failed to fetch PR diff ({resp.status_code}): {resp.text[:500]}")
    return resp.text


def review_diff(diff: str, api_key: str, model: str) -> str:
    truncated = diff[:MAX_DIFF_CHARS]
    note = "\n\n[diff truncated for length]" if len(diff) > MAX_DIFF_CHARS else ""

    resp = requests.post(
        GROQ_API,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": truncated + note},
            ],
            "temperature": 0.2,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        fail(f"Groq API call failed ({resp.status_code}): {resp.text[:500]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]


def post_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"body": f"### AI Code Review\n\n{body}"},
        timeout=30,
    )
    if resp.status_code != 201:
        fail(f"failed to post PR comment ({resp.status_code}): {resp.text[:500]}")


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

    review = review_diff(diff, api_key, model)
    post_comment(repo, pr_number, token, review)
    print("Posted review comment.")


if __name__ == "__main__":
    main()
