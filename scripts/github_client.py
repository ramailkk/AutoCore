import requests

from util import fail

GITHUB_API = "https://api.github.com"


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


def post_comment(repo: str, pr_number: str, token: str, body: str) -> None:
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"body": body},
        timeout=30,
    )
    if resp.status_code != 201:
        fail(f"failed to post PR comment ({resp.status_code}): {resp.text[:500]}")
