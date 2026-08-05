import os
import shutil
import string
import time

from github_client import post_comment
from util import fail

KERNEL_TEMPLATE_DIR = os.path.join("kaggle", "kernel_template")
KERNEL_RUN_DIR = os.path.join("kaggle", "kernel_run")
OUTPUT_DIR = os.path.join(KERNEL_RUN_DIR, "output")
SLUG = "core-heavy-review-check"
POLL_INTERVAL_SECONDS = 20
POLL_TIMEOUT_SECONDS = 20 * 60
DONE_STATES = {"complete", "error", "cancelled", "cancelAcknowledged"}


def render_template(path: str, values: dict) -> str:
    with open(path, encoding="utf-8") as f:
        template = f.read()
    return string.Template(template).safe_substitute(values)


def prepare_kernel_dir(kaggle_username: str, repo: str, pr_number: str) -> str:
    if os.path.exists(KERNEL_RUN_DIR):
        shutil.rmtree(KERNEL_RUN_DIR)
    os.makedirs(KERNEL_RUN_DIR)

    script = render_template(
        os.path.join(KERNEL_TEMPLATE_DIR, "heavy_review.py"),
        {"REPO": repo, "PR_NUMBER": pr_number},
    )
    with open(os.path.join(KERNEL_RUN_DIR, "heavy_review.py"), "w", encoding="utf-8") as f:
        f.write(script)

    metadata = render_template(
        os.path.join(KERNEL_TEMPLATE_DIR, "kernel-metadata.json"),
        {"KAGGLE_USERNAME": kaggle_username, "SLUG": SLUG},
    )
    with open(os.path.join(KERNEL_RUN_DIR, "kernel-metadata.json"), "w", encoding="utf-8") as f:
        f.write(metadata)

    return f"{kaggle_username}/{SLUG}"


def run_and_collect(kernel_slug: str) -> str:
    # Credentials come from ~/.kaggle/kaggle.json, written by the workflow's
    # "Configure Kaggle credentials" step. Use the package's own
    # auto-authenticated singleton (kaggle.api) rather than instantiating
    # KaggleApi() and calling .authenticate() ourselves — the package
    # auto-authenticates on import, and a second explicit authenticate()
    # call on a fresh instance 401s against it (known issue in the current
    # kaggle-cli: https://github.com/Kaggle/kaggle-cli/issues/882).
    import kaggle

    api = kaggle.api

    api.kernels_push(KERNEL_RUN_DIR)

    waited = 0
    while waited < POLL_TIMEOUT_SECONDS:
        status = api.kernels_status(kernel_slug)
        state = getattr(status, "status", None)
        print(f"kernel status: {state} (waited {waited}s)")
        if state in DONE_STATES:
            if state != "complete":
                fail(f"kernel run ended with status: {state}")
            break
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


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN") or fail("GITHUB_TOKEN not set")
    kaggle_username = os.environ.get("KAGGLE_USERNAME") or fail("KAGGLE_USERNAME not set")
    repo = os.environ.get("GITHUB_REPOSITORY") or fail("GITHUB_REPOSITORY not set")
    pr_number = os.environ.get("PR_NUMBER") or fail("PR_NUMBER not set")

    kernel_slug = prepare_kernel_dir(kaggle_username, repo, pr_number)
    result = run_and_collect(kernel_slug)

    post_comment(repo, pr_number, token, f"### Kaggle heavy tier (plumbing check)\n\n{result}")
    print("Posted heavy-tier plumbing check result.")


if __name__ == "__main__":
    main()
