"""Inventory loader. Scenario: MINOR — a small mechanical issue Ruff can
catch and auto-fix (unused import). Opening a PR that adds/touches this
file should classify as "minor" and generate_patch should use Ruff's own
auto-fix diff (no LLM patch call needed)."""

import json
import os


def load_inventory(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
