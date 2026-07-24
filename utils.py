def format_pr_summary(pr: dict) -> str:
    return f"PR #{pr['number']}: {pr['title']} by {pr['author']}"

def is_mergeable(pr: dict) -> bool:
    return pr.get("mergeable") and pr.get("state") == "open" and not pr.get("draft")

def count_changes(pr: dict) -> dict:
    return {
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "total": pr.get("additions", 0) + pr.get("deletions", 0),
    }
