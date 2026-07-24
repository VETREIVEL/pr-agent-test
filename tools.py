import json
import github

# Tool definitions for Claude API (raw JSON schema format)

TOOLS = [
    {
        "name": "list_open_prs",
        "description": "List all open pull requests in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_pr_details",
        "description": "Get metadata for a pull request: title, author, branch, file counts, merge status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "The PR number to fetch details for."},
            },
            "required": ["pr_number"],
        },
    },
    {
        "name": "get_pr_diff",
        "description": "Get the full unified diff of a pull request. Use this to review code changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "The PR number to fetch the diff for."},
            },
            "required": ["pr_number"],
        },
    },
    {
        "name": "get_pr_files",
        "description": "Get the list of files changed in a pull request with per-file diffs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "The PR number."},
            },
            "required": ["pr_number"],
        },
    },
    {
        "name": "get_ci_status",
        "description": "Get CI check results for a pull request (passing, failing, pending).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "The PR number."},
            },
            "required": ["pr_number"],
        },
    },
    {
        "name": "post_review",
        "description": "Post a review on a pull request. Use event=COMMENT for feedback, APPROVE to approve, REQUEST_CHANGES to request changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "The PR number."},
                "body": {"type": "string", "description": "The review summary text."},
                "event": {
                    "type": "string",
                    "enum": ["COMMENT", "APPROVE", "REQUEST_CHANGES"],
                    "description": "Review action.",
                },
            },
            "required": ["pr_number", "body", "event"],
        },
    },
    {
        "name": "merge_pr",
        "description": "Merge a pull request. Only call this after the user has explicitly confirmed they want to merge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pr_number": {"type": "integer", "description": "The PR number to merge."},
                "strategy": {
                    "type": "string",
                    "enum": ["merge", "squash", "rebase"],
                    "description": "Merge strategy. Default: squash.",
                },
            },
            "required": ["pr_number"],
        },
    },
]


def execute_tool(name: str, inputs: dict, repo: str) -> str:
    if name == "list_open_prs":
        result = github.list_open_prs(repo)
    elif name == "get_pr_details":
        result = github.get_pr_details(repo, inputs["pr_number"])
    elif name == "get_pr_diff":
        result = github.get_pr_diff(repo, inputs["pr_number"])
    elif name == "get_pr_files":
        result = github.get_pr_files(repo, inputs["pr_number"])
    elif name == "get_ci_status":
        result = github.get_ci_status(repo, inputs["pr_number"])
    elif name == "post_review":
        result = github.post_review(repo, inputs["pr_number"], inputs["body"], inputs["event"])
    elif name == "merge_pr":
        result = github.merge_pr(repo, inputs["pr_number"], inputs.get("strategy", "squash"))
    else:
        result = {"error": f"Unknown tool: {name}"}

    return json.dumps(result) if not isinstance(result, str) else result
