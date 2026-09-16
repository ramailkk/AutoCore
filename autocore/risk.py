"""Deterministic, config-driven risk scoring for a PR diff. Runs before any
LLM call — a cheap pre-triage pass, not a replacement for classify's own
judgment. A high-confidence score can force category="major" (see
autocore.nodes.node_classify); everything else here is pure computation,
no external calls, which is why it lives at the top level rather than under
integrations/ (no I/O) or models/ (produces a score, not a generation)."""

import re
from dataclasses import dataclass, field

import pathspec

_FILE_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)


@dataclass
class FileRisk:
    path: str
    patch: str
    score: float
    reasons: list[str] = field(default_factory=list)
    lines_changed: int = 0


def split_diff_by_file(diff: str) -> list[tuple[str, str]]:
    """Splits a raw unified diff (as returned by GitHub's .diff media type,
    covering every changed file) into [(path, patch_text), ...] in original
    order. Prefers the "b/" (new/renamed) path; falls back to "a/" for
    deletions, where the new path is /dev/null."""
    matches = list(_FILE_HEADER_RE.finditer(diff))
    if not matches:
        return []

    files = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(diff)
        patch = diff[start:end]
        a_path, b_path = m.group(1), m.group(2)
        path = b_path if b_path != "/dev/null" else a_path
        files.append((path, patch))
    return files


def _added_lines(patch: str) -> list[str]:
    return [
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def score_file(path: str, patch: str, cfg: dict) -> FileRisk:
    score = 0.0
    reasons: list[str] = []

    for rule in cfg.get("path_patterns", []):
        if pathspec.PathSpec.from_lines("gitwildmatch", [rule["pattern"]]).match_file(path):
            score += rule["points"]
            reasons.append(f"{rule['reason']} (+{rule['points']})")

    added = _added_lines(patch)
    added_text = "\n".join(added)
    for rule in cfg.get("content_patterns", []):
        if re.search(rule["pattern"], added_text):
            score += rule["points"]
            reasons.append(f"{rule['reason']} (+{rule['points']})")

    lines_changed = len(added)
    size_cfg = cfg.get("size", {})
    size_points = min(
        lines_changed * size_cfg.get("points_per_line", 0),
        size_cfg.get("max_points", 0),
    )
    if size_points:
        reasons.append(f"{lines_changed} lines changed (+{size_points:.1f})")
        score += size_points

    return FileRisk(path=path, patch=patch, score=score, reasons=reasons, lines_changed=lines_changed)


def score_diff(diff: str, cfg: dict) -> tuple[list[FileRisk], float]:
    """Returns (per-file risks sorted descending by score, PR-level score).
    The PR-level score is the max single-file score, not a sum — one
    genuinely risky file should trigger the override regardless of how many
    trivial files ride alongside it in the same PR; summing would let
    unrelated trivial changes inflate a false positive."""
    files = split_diff_by_file(diff)
    risks = [score_file(path, patch, cfg) for path, patch in files]
    risks.sort(key=lambda r: r.score, reverse=True)
    pr_score = risks[0].score if risks else 0.0
    return risks, pr_score


def is_forced_major(pr_score: float, cfg: dict) -> bool:
    return pr_score >= cfg.get("force_major_threshold", float("inf"))
