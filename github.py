import os
import requests

BASE_URL = "https://api.github.com"

def _headers():
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }

def get_pr_details(repo: str, pr_number: int) -> dict:
    r = requests.get(f"{BASE_URL}/repos/{repo}/pulls/{pr_number}", headers=_headers())
    r.raise_for_status()
    data = r.json()
    return {
        "number": data["number"],
        "title": data["title"],
        "body": data.get("body", ""),
        "author": data["user"]["login"],
        "base": data["base"]["ref"],
        "head": data["head"]["ref"],
        "state": data["state"],
        "mergeable": data.get("mergeable"),
        "mergeable_state": data.get("mergeable_state"),
        "draft": data.get("draft", False),
        "changed_files": data["changed_files"],
        "additions": data["additions"],
        "deletions": data["deletions"],
        "html_url": data["html_url"],
    }

def get_pr_diff(repo: str, pr_number: int) -> str:
    r = requests.get(
        f"{BASE_URL}/repos/{repo}/pulls/{pr_number}",
        headers={**_headers(), "Accept": "application/vnd.github.diff"},
    )
    r.raise_for_status()
    return r.text

def get_pr_files(repo: str, pr_number: int) -> list:
    r = requests.get(f"{BASE_URL}/repos/{repo}/pulls/{pr_number}/files", headers=_headers())
    r.raise_for_status()
    return [
        {
            "filename": f["filename"],
            "status": f["status"],
            "additions": f["additions"],
            "deletions": f["deletions"],
            "patch": f.get("patch", ""),
        }
        for f in r.json()
    ]

def get_ci_status(repo: str, pr_number: int) -> dict:
    pr = requests.get(f"{BASE_URL}/repos/{repo}/pulls/{pr_number}", headers=_headers()).json()
    sha = pr["head"]["sha"]
    r = requests.get(f"{BASE_URL}/repos/{repo}/commits/{sha}/check-runs", headers=_headers())
    r.raise_for_status()
    runs = r.json().get("check_runs", [])
    return {
        "total": len(runs),
        "passed": sum(1 for c in runs if c["conclusion"] == "success"),
        "failed": sum(1 for c in runs if c["conclusion"] == "failure"),
        "pending": sum(1 for c in runs if c["status"] == "in_progress"),
        "checks": [{"name": c["name"], "status": c["status"], "conclusion": c["conclusion"]} for c in runs],
    }

def post_review(repo: str, pr_number: int, body: str, event: str, comments: list = None) -> dict:
    payload = {"body": body, "event": event}
    if comments:
        payload["comments"] = comments
    r = requests.post(
        f"{BASE_URL}/repos/{repo}/pulls/{pr_number}/reviews",
        headers=_headers(),
        json=payload,
    )
    r.raise_for_status()
    return {"id": r.json()["id"], "state": r.json()["state"]}

def merge_pr(repo: str, pr_number: int, strategy: str = "squash", commit_message: str = "") -> dict:
    payload = {"merge_method": strategy}
    if commit_message:
        payload["commit_message"] = commit_message
    r = requests.put(
        f"{BASE_URL}/repos/{repo}/pulls/{pr_number}/merge",
        headers=_headers(),
        json=payload,
    )
    r.raise_for_status()
    data = r.json()
    return {"merged": data.get("merged", False), "sha": data.get("sha", ""), "message": data.get("message", "")}

def list_open_prs(repo: str) -> list:
    r = requests.get(f"{BASE_URL}/repos/{repo}/pulls?state=open", headers=_headers())
    r.raise_for_status()
    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "created_at": pr["created_at"],
            "html_url": pr["html_url"],
        }
        for pr in r.json()
    ]
