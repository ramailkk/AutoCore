"""Trivial file #1 in the mixed-risk scenario — should score near zero on
its own; the PR-level risk score should still be driven by auth/login.py."""


def greet(name: str) -> str:
    return f"Hi, {name}!"
