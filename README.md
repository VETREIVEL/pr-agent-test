# PR Agent

A conversational GitHub PR review agent powered by Google Gemini (Vertex AI). It can list open pull requests, fetch diffs, check CI status, post reviews, and merge PRs — all from a simple chat CLI.

## Prerequisites

- Python 3.11+
- A GCP project with Vertex AI API enabled
- A GitHub Personal Access Token (PAT) with `repo` scope
- `gcloud` authenticated (`gcloud auth application-default login`)

## Setup

**1. Clone and create a virtual environment**

```bash
git clone https://github.com/Prasanna030/pr-agent.git
cd pr-agent
python3 -m venv .venv
source .venv/bin/activate
```

**2. Install dependencies**

```bash
pip install --index-url https://pypi.org/simple/ -r requirements.txt
```

> The `--index-url` flag is needed if your pip is pointed at a private registry that doesn't mirror `google-cloud-aiplatform`.

**3. Configure environment**

Copy the example below into a `.env` file in the project root:

```env
GITHUB_TOKEN=ghp_...        # GitHub PAT with repo scope
GITHUB_REPO=owner/repo      # e.g. Prasanna030/pr-agent
GCP_PROJECT_ID=my-project   # GCP project with Vertex AI enabled
GCP_REGION=us-central1      # Vertex AI region
GEMINI_MODEL=gemini-2.5-flash  # optional — this is the default
```

`.env` is gitignored and will never be committed.

**4. Run**

```bash
python cli.py
```

## Usage

```
PR Review Agent — repo: owner/repo
Commands: 'list' to see open PRs, 'exit' to quit
Example: 'review PR #5' or 'what does PR 3 change?'

You: list
You: review PR #3
You: merge PR #3     ← agent will ask for confirmation before merging
You: exit
```

## How it works

| File | Role |
|---|---|
| `cli.py` | Read-eval-print loop; handles input/output |
| `agent.py` | Gemini chat session with agentic tool-use loop |
| `tools.py` | Tool schema definitions + dispatcher |
| `github.py` | GitHub REST API calls (list, diff, CI, review, merge) |

The agent uses Gemini's native function-calling to decide which GitHub tools to invoke. Merges are always intercepted and require explicit confirmation (`yes` / `no`) before execution.
