### Purpose
Automated pull request code review tool that leverages LLMs to analyze diffs and post contextual feedback. It operates in two tiers: a fast tier for standard reviews and a heavy tier that dispatches work to Kaggle kernels for GPU-accelerated or long-running analysis. Includes a bootstrapping step to generate a concise repository profile, giving the LLM accurate project context beyond filenames.

### Tech Stack
- **Language:** Python 3
- **Libraries:** `requests` (HTTP/API), `pathspec` (file filtering), `kaggle` (kernel management)
- **External Services:** GitHub API (diffs/comments), Groq API (LLM inference