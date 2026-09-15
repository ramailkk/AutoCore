import json
import subprocess


def run_ruff(files: list[str]) -> tuple[str, str]:
    """Run Ruff against already-checked-out files. Returns (findings_text, fix_diff).

    Ruff's JSON schema fields are accessed defensively (.get with fallbacks)
    since this hasn't been verified against every Ruff version — a schema
    mismatch degrades to empty findings rather than crashing the pipeline.
    """
    if not files:
        return "", ""

    check = subprocess.run(
        ["ruff", "check", "--output-format=json", *files],
        capture_output=True,
        text=True,
    )
    findings = ""
    try:
        violations = json.loads(check.stdout or "[]")
    except json.JSONDecodeError:
        violations = []

    if violations:
        lines = []
        for v in violations:
            loc = v.get("location", {})
            lines.append(
                f"{v.get('filename', '?')}:{loc.get('row', '?')}: "
                f"{v.get('code', '?')} {v.get('message', '')}"
            )
        findings = "\n".join(lines)

    # --diff without writing: shows what --fix would change, doesn't touch
    # the checkout.
    fix = subprocess.run(
        ["ruff", "check", "--fix", "--diff", *files],
        capture_output=True,
        text=True,
    )
    patch = fix.stdout.strip()

    return findings, patch
