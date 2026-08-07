import os
import subprocess
import sys

# Pinned to a narrow compatible window, not "latest":
# - >=4.44.2 needed so transformers' dynamic-module loader stops treating
#   DeepSeek's `if is_flash_attn_2_available(): import flash_attn` guard as
#   a hard requirement (fixed in huggingface/transformers#30954) — without
#   it, from_pretrained refuses to load unless flash_attn is installed,
#   even though it's never called under attn_implementation="eager".
# - latest transformers removed `is_torch_fx_available`, which DeepSeek's
#   modeling file still imports unconditionally, so anything past the
#   4.x series breaks the other way.
subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-q", "transformers==4.44.2", "accelerate", "bitsandbytes"]
)
import requests
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

REPO = "$REPO"
PR_NUMBER = "$PR_NUMBER"

# Kaggle Secrets (kaggle_secrets.UserSecretsClient, attached via the UI) do
# not carry over to kernels triggered through the API (kernels_push) — a
# known Kaggle API limitation. kernel-metadata.json has no env-var
# injection field either, so the dispatch script templates the token
# directly into this file before pushing.
os.environ["GITHUB_TOKEN"] = "$GITHUB_TOKEN"
# huggingface_hub reads HF_TOKEN from the environment automatically —
# avoids anonymous-download rate limits on the model pull below.
os.environ["HF_TOKEN"] = "$HF_TOKEN"

MODEL_ID = "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
MAX_DIFF_CHARS = 80_000

SYSTEM_PROMPT = (
    "You are a senior code reviewer doing a deep review of a pull request "
    "diff that a first-pass triage already flagged as high-risk (major). "
    "Read the diff and repo profile, then respond in exactly this format:\n\n"
    "=== REVIEW ===\n"
    "<detailed review: specific bugs/risks, file/line references where "
    "possible>\n"
    "=== PATCH ===\n"
    "<a minimal unified diff fixing the most important issue found, or the "
    "single word NONE if no safe automatic fix is possible>"
)


def fetch_diff(token: str) -> str:
    resp = requests.get(
        f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
        },
        timeout=30,
    )
    return resp.text if resp.status_code == 200 else ""


def fetch_profile(token: str) -> str:
    # Fetched live rather than templated in — profile text can contain
    # quotes/newlines that would break this file as a Python string
    # literal if substituted directly, same reasoning as the diff below.
    resp = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/.reviewer/profile.md",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw",
        },
        timeout=30,
    )
    return resp.text if resp.status_code == 200 else ""


def main() -> None:
    token = os.environ["GITHUB_TOKEN"]

    print(f"GPUs available: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        print(f"  {i}: {torch.cuda.get_device_name(i)}")

    diff = fetch_diff(token)[:MAX_DIFF_CHARS]
    profile = fetch_profile(token)

    print(f"Loading {MODEL_ID}...")
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quant_config,
        device_map="auto",
        trust_remote_code=True,
        # DeepSeek's custom modeling code only defines "eager" and
        # "flash_attention_2" (no "sdpa") — pin explicitly rather than
        # relying on auto-selection, and it also sidesteps flash_attn
        # entirely, which the P100 doesn't support anyway.
        attn_implementation="eager",
    )
    print("Model loaded.")

    user_prompt = ""
    if profile:
        user_prompt += f"# Repo profile\n\n{profile}\n\n"
    user_prompt += f"# Diff to review\n\n{diff}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    print("Generating review...")
    output = model.generate(**inputs, max_new_tokens=1024, do_sample=False)
    generated = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    with open("result.md", "w", encoding="utf-8") as f:
        f.write(generated)

    print(generated)


if __name__ == "__main__":
    main()
