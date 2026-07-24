# PR Agent

A GitHub PR review agent powered by Google Gemini (Vertex AI). It automatically reviews pull requests via webhooks and provides an interactive chat UI to manage PRs — list, review, check CI, and merge.

## Features

- **Webhook auto-review** — triggers on every PR opened/updated, posts a structured review automatically
- **Chat UI** — browser-based interface to chat with the agent interactively
- **Auto-reviews dashboard** — live feed of all webhook-triggered reviews
- **CLI** — original terminal chat interface still works
- **Safe merges** — merges always require explicit confirmation

## Prerequisites

- Python 3.11+
- A GCP project with Vertex AI API enabled
- A GitHub Personal Access Token (PAT) with `repo` scope
- `gcloud` authenticated (`gcloud auth application-default login`)
- An [ngrok](https://ngrok.com) account (free tier is enough)

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
pip install -r requirements.txt
```

**3. Configure environment**

Copy the values below into a `.env` file at the project root:

```env
GITHUB_TOKEN=ghp_...                    # GitHub PAT with repo scope
GITHUB_REPO=owner/repo                  # repo to watch for PRs
GCP_PROJECT_ID=my-project               # GCP project with Vertex AI enabled
GCP_REGION=us-central1                  # Vertex AI region
GEMINI_MODEL=gemini-2.5-flash           # optional, this is the default
GITHUB_WEBHOOK_SECRET=your-secret       # run: openssl rand -hex 20
PORT=8000                               # local server port
NGROK_AUTHTOKEN=your-ngrok-authtoken    # from dashboard.ngrok.com
```

`.env` is gitignored and will never be committed.

## Running

### Webhook server + Chat UI

```bash
python webhook.py
```

On startup it prints:
```
Webhook URL → set this in GitHub: https://xxxx.ngrok-free.app/webhook
Chat UI     → open in browser:    http://localhost:8000
```

**Register the webhook on GitHub:**
1. Go to your repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://xxxx.ngrok-free.app/webhook`
3. Content type: `application/json`
4. Secret: your `GITHUB_WEBHOOK_SECRET`
5. Events: select **Pull requests** only

### CLI (interactive chat)

```bash
python cli.py
```

```
You: list
You: review PR #3
You: merge PR #3     ← agent asks for confirmation before merging
You: exit
```

## How it works

```
PR opened/updated on GitHub
        ↓
GitHub sends webhook POST to /webhook
        ↓
Signature validated (HMAC-SHA256)
        ↓
Fetch PR diff + files from GitHub API
        ↓
Build prompt → call Gemini LLM
        ↓
Parse structured JSON response
        ↓
Post review back to GitHub PR
        ↓
Review card appears in Chat UI dashboard
```

## File structure

| File | Role |
|---|---|
| `webhook.py` | FastAPI server — webhook receiver, `/chat`, `/reviews`, ngrok tunnel |
| `agent.py` | Gemini chat session with tool-use loop + `auto_review()` for webhooks |
| `tools.py` | Tool schema definitions + dispatcher |
| `github.py` | GitHub REST API calls (list, diff, CI, review, merge) |
| `cli.py` | Terminal REPL interface |
| `static/index.html` | Browser-based chat UI + auto-reviews dashboard |
