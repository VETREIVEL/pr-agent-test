import hashlib
import hmac
import json
import logging
import os
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from pyngrok import ngrok

from agent import PRAgent
import github as gh

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI()
_agent: Optional[PRAgent] = None


def _get_agent() -> PRAgent:
    global _agent
    if _agent is None:
        _agent = PRAgent()
    return _agent


def _verify_signature(payload: bytes, signature: str) -> bool:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        log.warning("GITHUB_WEBHOOK_SECRET not set — skipping signature check")
        return True
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook")
async def handle_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    payload_bytes = await request.body()

    if not _verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    event = json.loads(payload_bytes)
    action = event.get("action", "")

    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    pr_number = event["pull_request"]["number"]
    repo = event["repository"]["full_name"]
    log.info("PR #%d %s in %s — starting review", pr_number, action, repo)

    try:
        agent = _get_agent()
        review = agent.auto_review(pr_number)
    except Exception as e:
        log.exception("auto_review failed for PR #%d", pr_number)
        return {"status": "error", "detail": str(e)}

    summary = review.get("summary", "")
    event_type = review.get("event", "COMMENT")
    inline_comments = review.get("inline_comments", [])

    # GitHub API expects inline comments to have position or line+side.
    # We pass them only if they have the required fields.
    formatted_comments = [
        {"path": c["path"], "line": c["line"], "body": c["body"], "side": "RIGHT"}
        for c in inline_comments
        if c.get("path") and c.get("line") and c.get("body")
    ]

    try:
        result = gh.post_review(
            repo=repo,
            pr_number=pr_number,
            body=summary,
            event=event_type,
            comments=formatted_comments or None,
        )
        log.info("Review posted for PR #%d — id=%s state=%s", pr_number, result["id"], result["state"])
    except Exception as e:
        log.exception("post_review failed for PR #%d", pr_number)
        return {"status": "error", "detail": str(e)}

    return {"status": "reviewed", "pr": pr_number, "event": event_type, "review_id": result["id"]}


def main():
    port = int(os.environ.get("PORT", 8000))

    authtoken = os.environ.get("NGROK_AUTHTOKEN", "")
    if authtoken:
        ngrok.set_auth_token(authtoken)

    tunnel = ngrok.connect(port, bind_tls=True)
    public_url = tunnel.public_url
    log.info("ngrok tunnel active: %s", public_url)
    print(f"\nWebhook URL → set this in GitHub: {public_url}/webhook\n")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
