import torch
import requests

REPO = "$REPO"
PR_NUMBER = "$PR_NUMBER"

# Kaggle Secrets (kaggle_secrets.UserSecretsClient) attached via the UI do
# not carry over to kernels triggered through the API (kernels_push) — this
# is a known Kaggle API limitation, not something fixable on our end. The
# token is instead delivered via a private dataset the dispatch script
# creates/updates before each push, mounted read-only under /kaggle/input.
TOKEN_PATH = "/kaggle/input/core-heavy-review-secrets/github_token.txt"


def main() -> None:
    with open(TOKEN_PATH, encoding="utf-8") as f:
        token = f.read().strip()

    gpu_lines = [f"GPUs available: {torch.cuda.device_count()}"]
    for i in range(torch.cuda.device_count()):
        gpu_lines.append(f"  {i}: {torch.cuda.get_device_name(i)}")

    resp = requests.get(
        f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
        },
        timeout=30,
    )
    diff_len = len(resp.text) if resp.status_code == 200 else -1

    result = (
        "# Kaggle heavy-tier plumbing check\n\n"
        + "\n".join(gpu_lines)
        + f"\n\nDiff fetch status: {resp.status_code}, length: {diff_len} chars\n\n"
        "Real heavy-model inference is not wired up yet. This run only "
        "validates GPU access and GitHub connectivity from inside a "
        "Kaggle kernel triggered via the API.\n"
    )

    with open("result.md", "w", encoding="utf-8") as f:
        f.write(result)

    print(result)


if __name__ == "__main__":
    main()
