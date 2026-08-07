import os
import shutil
import string
import time

from github_client import post_comment
from util import fail

KERNEL_TEMPLATE_DIR = os.path.join("kaggle", "kernel_template")
KERNEL_RUN_DIR = os.path.join("kaggle", "kernel_run")
OUTPUT_DIR = os.path.join(KERNEL_RUN_DIR, "output")
# Renamed from core-heavy-review-check now that this runs real inference,
# not just the GPU/connectivity plumbing check — creates a new Kaggle
# kernel entity; the old "-check" one is left behind, harmless.
KERNEL_SLUG = "core-heavy-review"

POLL_INTERVAL_SECONDS = 20
# Real model download + 4-bit load + generation is unverified timing —
# 20 min (the old plumbing-check budget) is almost certainly too short.
# 40 min is a rough guess pending an actual observed run.
POLL_TIMEOUT_SECONDS = 40 * 60
# COMPLETE is confirmed from a real run's enum repr. These failure-state
# names are a best guess (not yet observed) — if a run hits an unrecognized
# terminal state, it'll fall through to the POLL_TIMEOUT_SECONDS failure
# instead of this one, which will still surface in the logs via the raw
# status print above.
DONE_STATES = {"ERROR", "CANCELLED", "CANCELED", "CANCEL_ACKNOWLEDGED", "CANCEL_REQUESTED"}


def render_template(path: str, values: dict) -> str:
    with open(path, encoding="utf-8") as f:
        template = f.read()
    return string.Template(template).safe_substitute(values)


def prepare_kernel_dir(
    kaggle_username: str, repo: str, pr_number: str, github_token: str, hf_token: str = ""
) -> str:
    if os.path.exists(KERNEL_RUN_DIR):
        shutil.rmtree(KERNEL_RUN_DIR)
    os.makedirs(KERNEL_RUN_DIR)

    script = render_template(
        os.path.join(KERNEL_TEMPLATE_DIR, "heavy_review.py"),
        {"REPO": repo, "PR_NUMBER": pr_number, "GITHUB_TOKEN": github_token, "HF_TOKEN": hf_token},
    )
    with open(os.path.join(KERNEL_RUN_DIR, "heavy_review.py"), "w", encoding="utf-8") as f:
        f.write(script)

    metadata = render_template(
        os.path.join(KERNEL_TEMPLATE_DIR, "kernel-metadata.json"),
        {"KAGGLE_USERNAME": kaggle_username, "SLUG": KERNEL_SLUG},
    )
    with open(os.path.join(KERNEL_RUN_DIR, "kernel-metadata.json"), "w", encoding="utf-8") as f:
        f.write(metadata)

    return f"{kaggle_username}/{KERNEL_SLUG}"


def run_and_collect(api, kernel_slug: str) -> str:
    print(f"Pushing kernel {kernel_slug} to Kaggle...")
    api.kernels_push(KERNEL_RUN_DIR)
    print("Push call returned, polling for status...")

    waited = 0
    while waited < POLL_TIMEOUT_SECONDS:
        status = api.kernels_status(kernel_slug)
        # api.kernels_status returns a KernelWorkerStatus enum member, not a
        # plain string — confirmed from a real run (repr looks like
        # `<KernelWorkerStatus.COMPLETE: 2>`). Compare by .name, not by
        # equality with a string.
        state = getattr(status, "status", None)
        state_name = getattr(state, "name", str(state))
        print(f"kernel status: {state_name} (waited {waited}s) raw={status!r}")
        if state_name == "COMPLETE":
            break
        if state_name in DONE_STATES:
            failure_message = getattr(status, "failure_message", None)
            fail(f"kernel run ended with status: {state_name} ({failure_message})")
        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS
    else:
        fail(f"kernel did not finish within {POLL_TIMEOUT_SECONDS}s")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    api.kernels_output(kernel_slug, path=OUTPUT_DIR, force=True)

    result_path = os.path.join(OUTPUT_DIR, "result.md")
    if not os.path.exists(result_path):
        fail(f"expected output file not found: {result_path}")

    with open(result_path, encoding="utf-8") as f:
        return f.read()


def parse_heavy_result(text: str) -> tuple[str, str]:
    """Split heavy_review.py's `=== REVIEW === / === PATCH ===` output into
    (review, patch). patch is "" if the model found no safe fix (or the
    marker's missing entirely, e.g. an older kernel run)."""
    if "=== PATCH ===" not in text:
        return text.strip(), ""
    review_part, _, patch_part = text.partition("=== PATCH ===")
    review = review_part.replace("=== REVIEW ===", "", 1).strip()
    patch = patch_part.strip()
    if patch.upper() == "NONE":
        patch = ""
    return review, patch


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN") or fail("GITHUB_TOKEN not set")
    kaggle_username = os.environ.get("KAGGLE_USERNAME") or fail("KAGGLE_USERNAME not set")
    repo = os.environ.get("GITHUB_REPOSITORY") or fail("GITHUB_REPOSITORY not set")
    pr_number = os.environ.get("PR_NUMBER") or fail("PR_NUMBER not set")
    # Optional — DeepSeek-Coder-V2-Lite-Instruct isn't gated, HF_TOKEN just
    # avoids anonymous-download rate limits.
    hf_token = os.environ.get("HF_TOKEN", "")

    # Credentials come from ~/.kaggle/kaggle.json, written by the workflow's
    # "Configure Kaggle credentials" step. Use the package's own
    # auto-authenticated singleton (kaggle.api) rather than instantiating
    # KaggleApi() and calling .authenticate() ourselves — the package
    # auto-authenticates on import, and a second explicit authenticate()
    # call on a fresh instance 401s against it (known issue in the current
    # kaggle-cli: https://github.com/Kaggle/kaggle-cli/issues/882).
    import kaggle

    api = kaggle.api

    kernel_slug = prepare_kernel_dir(kaggle_username, repo, pr_number, token, hf_token)
    result = run_and_collect(api, kernel_slug)
    review, patch = parse_heavy_result(result)

    body = f"### Kaggle heavy tier (standalone run)\n\n{review}"
    if patch:
        body += f"\n\n<details><summary>Suggested patch</summary>\n\n```diff\n{patch}\n```\n</details>"

    post_comment(repo, pr_number, token, body)
    print("Posted heavy-tier review result.")


if __name__ == "__main__":
    main()
