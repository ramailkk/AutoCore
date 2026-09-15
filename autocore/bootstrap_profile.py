import os

import pathspec

from autocore.config import load_config
from autocore.models.llm_client import chat
from autocore.prompts import load_prompt
from autocore.util import fail

ALWAYS_IGNORE = {".git", ".reviewer", "__pycache__", "node_modules", ".venv", "venv"}
KEY_FILE_NAMES = {
    "readme.md",
    "readme",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "go.mod",
    "cargo.toml",
    "pom.xml",
    "build.gradle",
    "gemfile",
    "composer.json",
}
KEY_FILE_MAX_CHARS = 3_000

# Key files (README, manifests) tell us what a repo claims to be. They're
# often thin or missing. Sampling actual source files gives the model real
# code to infer intent from, so the profile covers the gist of what the
# repo does even when the docs don't say.
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".rb", ".php", ".c", ".cpp", ".h", ".cs", ".kt", ".swift",
}
ENTRY_POINT_HINTS = ("main", "index", "app", "cli", "server", "__init__")
SAMPLE_MAX_FILES = 8
SAMPLE_MAX_CHARS = 1_500
TREE_MAX_ENTRIES = 500


def load_ignore_spec(root: str) -> pathspec.PathSpec:
    gitignore_path = os.path.join(root, ".gitignore")
    lines = []
    if os.path.exists(gitignore_path):
        with open(gitignore_path, encoding="utf-8") as f:
            lines = f.readlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def scan_repo(root: str) -> tuple[list[str], dict[str, str], list[str]]:
    spec = load_ignore_spec(root)
    tree: list[str] = []
    key_files: dict[str, str] = {}
    source_candidates: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = [
            d
            for d in dirnames
            if d not in ALWAYS_IGNORE
            and not spec.match_file(os.path.join(rel_dir, d) if rel_dir != "." else d)
        ]

        for name in filenames:
            rel_path = os.path.join(rel_dir, name) if rel_dir != "." else name
            if spec.match_file(rel_path):
                continue
            if len(tree) < TREE_MAX_ENTRIES:
                tree.append(rel_path)

            if name.lower() in KEY_FILE_NAMES:
                abs_path = os.path.join(dirpath, name)
                try:
                    with open(abs_path, encoding="utf-8", errors="ignore") as f:
                        key_files[rel_path] = f.read()[:KEY_FILE_MAX_CHARS]
                except OSError:
                    pass
            elif os.path.splitext(name)[1].lower() in SOURCE_EXTENSIONS:
                source_candidates.append(rel_path)

    return tree, key_files, source_candidates


def pick_source_sample(root: str, candidates: list[str]) -> dict[str, str]:
    def rank(rel_path: str) -> tuple[int, int]:
        base = os.path.splitext(os.path.basename(rel_path))[0].lower()
        is_hinted = any(hint in base for hint in ENTRY_POINT_HINTS)
        depth = rel_path.count(os.sep)
        return (0 if is_hinted else 1, depth)

    picked = sorted(candidates, key=rank)[:SAMPLE_MAX_FILES]

    samples: dict[str, str] = {}
    for rel_path in picked:
        try:
            with open(os.path.join(root, rel_path), encoding="utf-8", errors="ignore") as f:
                samples[rel_path] = f.read()[:SAMPLE_MAX_CHARS]
        except OSError:
            pass
    return samples


def build_prompt(tree: list[str], key_files: dict[str, str], samples: dict[str, str]) -> str:
    parts = ["## File tree", "\n".join(tree)]
    for path, content in key_files.items():
        parts.append(f"## {path}\n\n{content}")
    for path, content in samples.items():
        parts.append(f"## Sampled source: {path}\n\n{content}")
    return "\n\n".join(parts)


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY") or fail("GROQ_API_KEY not set")
    model = load_config()["groq"]["model"]
    root = os.environ.get("REPO_ROOT", ".")
    profile_path = load_config()["profile"]["path"]

    tree, key_files, source_candidates = scan_repo(root)
    samples = pick_source_sample(root, source_candidates)
    prompt = build_prompt(tree, key_files, samples)

    profile = chat(load_prompt("bootstrap_profile_system"), prompt, api_key, model)

    os.makedirs(os.path.dirname(profile_path), exist_ok=True)
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(profile)

    print(f"Wrote {profile_path}")


if __name__ == "__main__":
    main()
