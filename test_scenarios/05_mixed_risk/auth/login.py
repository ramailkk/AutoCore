"""Login check. Scenario: MIXED RISK, risky file. Deliberately touches
auth/ and uses eval() so the deterministic risk scorer (autocore/risk.py)
scores this file above force_major_threshold on its own, even though the
other files in this same PR are trivial."""

import subprocess


def check(user: str, password_expr: str) -> bool:
    return eval(password_expr) == user
