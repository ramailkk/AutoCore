"""Graph wiring and the entry point for the main PR-review flow. Node
behavior lives in autocore/nodes.py, routing decisions in
autocore/routing.py, parameters in autocore/config.yaml."""

import os

from langgraph.graph import END, StateGraph

from autocore.config import load_config
from autocore.integrations.github_client import get_diff
from autocore.nodes import (
    node_classify,
    node_deep_review,
    node_generate_patch,
    node_open_pr,
    node_post_comment,
    node_static_analysis,
)
from autocore.routing import decide_action, route_by_category
from autocore.state import ReviewState
from autocore.util import fail


def load_profile() -> str:
    path = load_config()["profile"]["path"]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


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
    # Only required if the pipeline actually reaches generate_patch/deep_review
    # for this diff — checked lazily inside those nodes, not here, so
    # advice/none-only usage works without every secret configured.
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
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
        "openrouter_key": openrouter_key,
        "kaggle_username": kaggle_username,
        "hf_token": hf_token,
        "diff": diff,
        "profile": load_profile(),
    }

    graph = build_graph()
    graph.invoke(state)


if __name__ == "__main__":
    main()
