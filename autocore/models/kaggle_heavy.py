import os
import re
import shutil
import string
import subprocess
import time

from autocore.config import load_config
from autocore.integrations.github_client import post_comment
from autocore.util import fail

KERNEL_TEMPLATE_DIR = os.path.join("kaggle", "kernel_template")
KERNEL_RUN_DIR = os.path.join("kaggle", "kernel_run")
OUTPUT_DIR = os.path.join(KERNEL_RUN_DIR, "output")


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

    kernel_slug = load_config()["kaggle"]["kernel_slug"]

    script = render_template(
        os.path.join(KERNEL_TEMPLATE_DIR, "heavy_review.py"),
        {"REPO": repo, "PR_NUMBER": pr_number, "GITHUB_TOKEN": github_token, "HF_TOKEN": hf_token},
    )
    with open(os.path.join(KERNEL_RUN_DIR, "heavy_review.py"), "w", encoding="utf-8") as f:
        f.write(script)

    metadata = render_template(
        os.path.join(KERNEL_TEMPLATE_DIR, "kernel-metadata.json"),
        {"KAGGLE_USERNAME": kaggle_username, "SLUG": kernel_slug},
    )
    with open(os.path.join(KERNEL_RUN_DIR, "kernel-metadata.json"), "w", encoding="utf-8") as f:
        f.write(metadata)

    return f"{kaggle_username}/{kernel_slug}"


def run_and_collect(api, kernel_slug: str) -> str:
    cfg = load_config()["kaggle"]

    print(f"Pushing kernel {kernel_slug} to Kaggle...")
    try:
        subprocess.run(
            ["kaggle", "kernels", "push", "-p", KERNEL_RUN_DIR, "--accelerator", cfg["accelerator"]],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        fail(f"kernel push failed: {e}")
    print("Push call returned, polling for status...")

    poll_interval = cfg["poll_interval_seconds"]
    poll_timeout = cfg["poll_timeout_seconds"]
    done_states = set(cfg["done_states"])

    waited = 0
    while waited < poll_timeout:
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
        if state_name in done_states:
            failure_message = getattr(status, "failure_message", None)
            fail(f"kernel run ended with status: {state_name} ({failure_message})")
        time.sleep(poll_interval)
        waited += poll_interval
    else:
        fail(f"kernel did not finish within {poll_timeout}s")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    api.kernels_output(kernel_slug, path=OUTPUT_DIR, force=True)

    result_path = os.path.join(OUTPUT_DIR, "result.md")
    if not os.path.exists(result_path):
        fail(f"expected output file not found: {result_path}")

    with open(result_path, encoding="utf-8") as f:
        return f.read()


def parse_heavy_result(text: str) -> tuple[str, str]:
    """Split heavy_review.py's `=== REVIEW === / === PATCH ===` output into
    (review, patch).

    Observed in practice: the model doesn't reliably emit the literal
    "=== PATCH ===" marker even when asked — it sometimes writes a
    markdown heading like "**Patch:**" instead, with the diff still
    fenced as ```diff. Falls back to pulling the diff out of that fence
    when the exact marker isn't found, rather than silently losing a
    patch the model did produce."""
    if "=== PATCH ===" in text:
        review_part, _, patch_part = text.partition("=== PATCH ===")
        review = review_part.replace("=== REVIEW ===", "", 1).strip()
        patch = patch_part.strip()
        if patch.upper() == "NONE":
            patch = ""
        return review, patch

    fence = re.search(r"```diff\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        patch = fence.group(1).strip()
        review = (text[: fence.start()] + text[fence.end() :]).strip()
        review = review.replace("=== REVIEW ===", "", 1).strip()
        return review, patch

    return text.strip(), ""


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
