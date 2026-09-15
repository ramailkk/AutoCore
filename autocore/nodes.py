"""Graph node implementations. Each node reads/writes the shared
ReviewState and delegates actual work to autocore.models (LLM/Kaggle
calls) and autocore.integrations (GitHub/Ruff). Routing decisions
(which node runs next) live in autocore/routing.py, not here."""

import json
import os
import subprocess

from autocore.config import load_config
from autocore.integrations.github_client import (
    create_pull_request,
    find_pull_request,
    get_changed_python_files,
    post_comment,
)
from autocore.integrations.ruff import run_ruff
from autocore.models.kaggle_heavy import parse_heavy_result, prepare_kernel_dir, run_and_collect
from autocore.models.llm_client import chat
from autocore.prompts import load_prompt
from autocore.state import ReviewState
from autocore.util import fail, strip_code_fence


def node_static_analysis(state: ReviewState) -> dict:
    py_files = [
        f
        for f in get_changed_python_files(state["repo"], state["pr_number"], state["token"])
        if os.path.exists(f)
    ]
    findings, patch = run_ruff(py_files)
    print(
        f"Ruff: {len(findings.splitlines()) if findings else 0} findings, "
        f"{'has' if patch else 'no'} auto-fix diff"
    )
    return {"ruff_findings": findings, "ruff_patch": patch}


def node_classify(state: ReviewState) -> dict:
    cfg = load_config()["classify"]
    max_diff_chars = cfg["max_diff_chars"]
    valid_categories = set(cfg["categories"])

    diff = state["diff"][:max_diff_chars]
    note = "\n\n[diff truncated for length]" if len(state["diff"]) > max_diff_chars else ""

    user_prompt = ""
    if state.get("profile"):
        user_prompt += f"# Repo profile\n\n{state['profile']}\n\n"
    if state.get("ruff_findings"):
        user_prompt += f"# Static analysis findings (Ruff)\n\n{state['ruff_findings']}\n\n"
    user_prompt += f"# Diff to review\n\n{diff}{note}"

    groq_model = load_config()["groq"]["model"]
    raw = chat(load_prompt("classify_system"), user_prompt, state["groq_key"], groq_model)

    try:
        data = json.loads(strip_code_fence(raw))
        category = str(data.get("category", "")).lower()
        review = str(data.get("review", "")).strip()
        if category not in valid_categories or not review:
            raise ValueError("missing or invalid category/review field")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARNING: could not parse classification JSON ({e}); falling back to major/raw text")
        category = "major"
        review = raw

    print(f"Classified as: {category}")
    return {"category": category, "review": review}


def node_generate_patch(state: ReviewState) -> dict:
    if state.get("ruff_patch"):
        print("Using Ruff's own auto-fix diff as the patch (no LLM call needed).")
        return {"patch": state["ruff_patch"]}

    if not state.get("openrouter_key"):
        fail("OPENROUTER_API_KEY not set (needed for patch generation beyond Ruff's own fixes)")

    max_diff_chars = load_config()["classify"]["max_diff_chars"]
    user_prompt = (
        (f"# Repo profile\n\n{state['profile']}\n\n" if state.get("profile") else "")
        + f"# Reviewer's note on the minor issue\n\n{state['review']}\n\n"
        + f"# Diff\n\n{state['diff'][:max_diff_chars]}"
    )
    openrouter_model = load_config()["openrouter"]["model"]
    patch = chat(
        load_prompt("patch_system"),
        user_prompt,
        state["openrouter_key"],
        openrouter_model,
        provider="openrouter",
    )
    return {"patch": patch.strip()}


def node_deep_review(state: ReviewState) -> dict:
    if not state.get("kaggle_username"):
        fail("KAGGLE_USERNAME not set (needed for heavy-tier review)")

    import kaggle

    api = kaggle.api
    kernel_slug = prepare_kernel_dir(
        state["kaggle_username"],
        state["repo"],
        state["pr_number"],
        state["token"],
        state.get("hf_token", ""),
    )
    result = run_and_collect(api, kernel_slug)
    review, patch = parse_heavy_result(result)

    out = {"review": review}
    if patch:
        out["patch"] = patch
    return out


def node_open_pr(state: ReviewState) -> dict:
    repo, pr_number, category = state["repo"], state["pr_number"], state["category"]
    base = state.get("pr_head_ref")
    if not base:
        print("WARNING: PR_HEAD_REF not set; falling back to commenting the patch.")
        return {}
    # Stable name, not unique-per-run: re-runs (e.g. new commits pushed to
    # the human's PR) force-push the same branch and update the same bot
    # PR, rather than piling up duplicates.
    branch = f"bot/fix-{pr_number}-{category}"

    patch_file = os.path.join(os.sep, "tmp", "bot.patch")
    with open(patch_file, "w", encoding="utf-8") as f:
        f.write(state["patch"] + "\n")

    git_steps = [
        # The workflow already checks out the PR's actual head branch
        # (`ref: github.head_ref`), so branching off current HEAD is the
        # base — no need to fetch/checkout origin/<base> separately, which
        # would depend on remote-tracking refs behaving a particular way
        # under actions/checkout's shallow clone.
        ["git", "checkout", "-B", branch],
        ["git", "apply", "--recount", patch_file],
        ["git", "config", "user.name", "github-actions[bot]"],
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        ["git", "add", "-A"],
        ["git", "commit", "-m", f"Automated fix: {category} issue on PR #{pr_number}"],
        ["git", "push", "--force", "origin", branch],
    ]
    for step in git_steps:
        result = subprocess.run(step, capture_output=True, text=True)
        if result.returncode != 0:
            # Most likely culprit: an LLM-generated patch (OpenRouter or the
            # Kaggle heavy tier) didn't apply cleanly — those aren't as
            # reliably well-formed as Ruff's own diffs. Fall back to
            # commenting the patch as text rather than losing it entirely.
            print(f"WARNING: '{' '.join(step)}' failed: {result.stderr}")
            print("Falling back to commenting the patch instead of opening a PR.")
            return {}

    title = f"Automated fix: {category} issue (from PR #{pr_number})"
    body = f"Suggested fix for the issue found on #{pr_number}.\n\n{state['review']}"
    pr = create_pull_request(repo, branch, base, title, body, state["token"])
    if pr is None:
        pr = find_pull_request(repo, branch, base, state["token"])
        if pr is None:
            print("WARNING: PR creation returned 422 but no matching open PR found; "
                  "falling back to commenting the patch instead.")
            return {}

    print(f"Opened/updated PR: {pr['html_url']}")
    return {"pr_url": pr["html_url"]}


def node_post_comment(state: ReviewState) -> dict:
    labels = load_config()["classify"]["labels"]
    label = labels.get(state["category"], state["category"])
    if state.get("pr_url"):
        body = f"AI Code Review — {label}\n\nOpened {state['pr_url']} with a suggested fix."
    else:
        body = f"AI Code Review — {label}\n\n{state['review']}"
        if state.get("patch"):
            body += (
                "\n\n<details><summary>Suggested patch</summary>\n\n"
                f"```diff\n{state['patch']}\n```\n</details>"
            )
    post_comment(state["repo"], state["pr_number"], state["token"], body)
    print("Posted review comment.")
    return {}
