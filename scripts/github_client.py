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


def get_changed_python_files(repo: str, pr_number: str, token: str) -> list[str]:
    """Filenames of non-deleted .py files changed in the PR, capped at the
    first 100 (one page) — fine for typical PR sizes, will undercount on
    huge PRs since pagination isn't implemented yet."""
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files"
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        params={"per_page": 100},
        timeout=30,
    )
    if resp.status_code != 200:
        fail(f"failed to fetch PR files ({resp.status_code}): {resp.text[:500]}")

    return [
        f["filename"]
        for f in resp.json()
        if f.get("status") != "removed" and f.get("filename", "").endswith(".py")
    ]


def create_pull_request(
    repo: str, head: str, base: str, title: str, body: str, token: str
) -> dict | None:
    """Opens a PR. Returns None (not a failure) on 422 — that means a PR for
    this head branch already exists, which happens on re-runs since
    node_open_pr force-pushes to a stable per-PR-per-category branch name
    rather than creating a new one each time. Caller should fall back to
    find_pull_request() in that case."""
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": title, "head": head, "base": base, "body": body},
        timeout=30,
    )
    if resp.status_code == 422:
        return None
    if resp.status_code != 201:
        fail(f"failed to create PR ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def find_pull_request(repo: str, head: str, base: str, token: str) -> dict | None:
    owner = repo.split("/")[0]
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        params={"head": f"{owner}:{head}", "base": base, "state": "open"},
        timeout=30,
    )
    if resp.status_code != 200:
        fail(f"failed to look up existing PR ({resp.status_code}): {resp.text[:500]}")
    results = resp.json()
    return results[0] if results else None


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
