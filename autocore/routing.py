"""Pure routing decisions for the review graph. Kept isolated from node
logic (autocore/nodes.py) so the "what happens" (node implementations) and
"where does it go next" (this file) can change independently."""

from autocore.state import ReviewState


def route_by_category(state: ReviewState) -> str:
    return state["category"]


def decide_action(state: ReviewState) -> str:
    # Deliberately isolated as one small function reading only category +
    # patch-presence, not folded into the graph wiring — swap this for a
    # model call later (e.g. to weigh confidence, blast radius) without
    # touching anything else.
    if state.get("patch"):
        return "open_pr"
    return "post_comment"
