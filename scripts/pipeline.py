import json
import os
import subprocess
from typing import TypedDict

from langgraph.graph import END, StateGraph

from github_client import (
    create_pull_request,
    find_pull_request,
    get_changed_python_files,
    get_diff,
    post_comment,
)
from kaggle_dispatch import parse_heavy_result, prepare_kernel_dir, run_and_collect
from llm_client import chat
from static_analysis import run_ruff
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

CLASSIFY_SYSTEM_PROMPT = (
    "You are a concise code reviewer. You will be given a pull request diff, "
    "optionally preceded by a repo profile and static analysis (Ruff) "
    "findings for context. Ruff already covers mechanical lint issues — "
    "focus your own judgment on things it can't catch: real bugs, security "
    "issues, risky logic, architecture concerns. Be specific (file/line if "
    "visible in the diff).\n\n"
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

PATCH_SYSTEM_PROMPT = (
    "You are a precise code-patching assistant. You will be given a pull "
    "request diff, a repo profile for context, and a reviewer's description "
    "of a minor issue in that diff. Produce a minimal unified diff patch "
    "(git diff format) that fixes ONLY that issue. Do not touch unrelated "
    "code, do not reformat, do not add commentary. Output only the diff."
)


class ReviewState(TypedDict, total=False):
    repo: str
    pr_number: str
    pr_head_ref: str
    token: str
    groq_key: str
    groq_model: str
    openrouter_key: str
    openrouter_model: str
    kaggle_username: str
    hf_token: str
    diff: str
    profile: str
    ruff_findings: str
    ruff_patch: str
    category: str
    review: str
    patch: str
    pr_url: str


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
    diff = state["diff"][:MAX_DIFF_CHARS]
    note = "\n\n[diff truncated for length]" if len(state["diff"]) > MAX_DIFF_CHARS else ""

    user_prompt = ""
    if state.get("profile"):
        user_prompt += f"# Repo profile\n\n{state['profile']}\n\n"
    if state.get("ruff_findings"):
        user_prompt += f"# Static analysis findings (Ruff)\n\n{state['ruff_findings']}\n\n"
    user_prompt += f"# Diff to review\n\n{diff}{note}"

    raw = chat(CLASSIFY_SYSTEM_PROMPT, user_prompt, state["groq_key"], state["groq_model"])

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

    print(f"Classified as: {category}")
    return {"category": category, "review": review}


def route_by_category(state: ReviewState) -> str:
    return state["category"]


def node_generate_patch(state: ReviewState) -> dict:
    if state.get("ruff_patch"):
        print("Using Ruff's own auto-fix diff as the patch (no LLM call needed).")
        return {"patch": state["ruff_patch"]}

    if not state.get("openrouter_key"):
        fail("OPENROUTER_API_KEY not set (needed for patch generation beyond Ruff's own fixes)")

    user_prompt = (
        (f"# Repo profile\n\n{state['profile']}\n\n" if state.get("profile") else "")
        + f"# Reviewer's note on the minor issue\n\n{state['review']}\n\n"
        + f"# Diff\n\n{state['diff'][:MAX_DIFF_CHARS]}"
    )
    patch = chat(
        PATCH_SYSTEM_PROMPT,
        user_prompt,
        state["openrouter_key"],
        state["openrouter_model"],
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


def decide_action(state: ReviewState) -> str:
    # Deliberately isolated as one small function reading only category +
    # patch-presence, not folded into the graph wiring — swap this for a
    # model call later (e.g. to weigh confidence, blast radius) without
    # touching anything else.
    if state.get("patch"):
        return "open_pr"
    return "post_comment"


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
    label = LABELS.get(state["category"], state["category"])
    if state.get("pr_url"):
        body = f"### AI Code Review — {label}\n\nOpened {state['pr_url']} with a suggested fix."
    else:
        body = f"### AI Code Review — {label}\n\n{state['review']}"
        if state.get("patch"):
            body += (
                "\n\n<details><summary>Suggested patch</summary>\n\n"
                f"```diff\n{state['patch']}\n```\n</details>"
            )
    post_comment(state["repo"], state["pr_number"], state["token"], body)
    print("Posted review comment.")
    return {}


def build_graph():
    g = StateGraph(ReviewState)
    g.add_node("static_analysis", node_static_analysis)
    g.add_node("classify", node_classify)
    g.add_node("generate_patch", node_generate_patch)
    g.add_node("deep_review", node_deep_review)
    g.add_node("open_pr", node_open_pr)
    g.add_node("post_comment", node_post_comment)

    g.set_entry_point("static_analysis")
    g.add_edge("static_analysis", "classify")
    g.add_conditional_edges(
        "classify",
        route_by_category,
        {
            "minor": "generate_patch",
            "major": "deep_review",
            "advice": "post_comment",
            "none": "post_comment",
        },
    )
    action_routes = {"open_pr": "open_pr", "post_comment": "post_comment"}
    g.add_conditional_edges("generate_patch", decide_action, action_routes)
    g.add_conditional_edges("deep_review", decide_action, action_routes)
    g.add_edge("open_pr", "post_comment")
    g.add_edge("post_comment", END)
    return g.compile()


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN") or fail("GITHUB_TOKEN not set")
    groq_key = os.environ.get("GROQ_API_KEY") or fail("GROQ_API_KEY not set")
    repo = os.environ.get("GITHUB_REPOSITORY") or fail("GITHUB_REPOSITORY not set")
    pr_number = os.environ.get("PR_NUMBER") or fail("PR_NUMBER not set")
    # Only required if the pipeline reaches open_pr — checked there, not
    # here, so advice/none/comment-only paths don't need it.
    pr_head_ref = os.environ.get("PR_HEAD_REF", "")
    groq_model = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")
    # Only required if the pipeline actually reaches generate_patch/deep_review
    # for this diff — checked lazily inside those nodes, not here, so
    # advice/none-only usage works without every secret configured.
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    openrouter_model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3-coder:free")
    kaggle_username = os.environ.get("KAGGLE_USERNAME", "")
    hf_token = os.environ.get("HF_TOKEN", "")

    diff = get_diff(repo, pr_number, token)
    if not diff.strip():
        print("Empty diff, nothing to review.")
        return

    state: ReviewState = {
        "repo": repo,
        "pr_number": pr_number,
        "pr_head_ref": pr_head_ref,
        "token": token,
        "groq_key": groq_key,
        "groq_model": groq_model,
        "openrouter_key": openrouter_key,
        "openrouter_model": openrouter_model,
        "kaggle_username": kaggle_username,
        "hf_token": hf_token,
        "diff": diff,
        "profile": load_profile(),
    }

    graph = build_graph()
    graph.invoke(state)


if __name__ == "__main__":
    main()
