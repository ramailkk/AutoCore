import torch
import requests
from kaggle_secrets import UserSecretsClient

REPO = "$REPO"
PR_NUMBER = "$PR_NUMBER"


def main() -> None:
    secrets = UserSecretsClient()
    token = secrets.get_secret("GITHUB_TOKEN")

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
