from typing import TypedDict


class ReviewState(TypedDict, total=False):
    repo: str
    pr_number: str
    pr_head_ref: str
    token: str
    groq_key: str
    openrouter_key: str
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
    risk_score: float
    risk_reasons: list[str]
