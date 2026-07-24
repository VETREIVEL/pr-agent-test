from dataclasses import dataclass, field

@dataclass
class Skill:
    name: str
    description: str           # shown in listings
    prompt: str                # injected into system prompt
    triggers: list[str]        # example phrases that activate this skill
    tools: list[str]           # tools this skill uses
    confirmation_required: bool = False
    confirmation_prompt: str = ""


SKILLS: list[Skill] = [
    Skill(
        name="list_prs",
        description="List all open pull requests",
        prompt="When the user asks to list or show PRs, call list_open_prs and present the results clearly.",
        triggers=["list", "show open PRs", "what PRs are open"],
        tools=["list_open_prs"],
    ),
    Skill(
        name="inspect_pr",
        description="Fetch and summarise PR metadata and changed files",
        prompt="When the user asks what a PR changes or wants details, call get_pr_details and get_pr_files and summarise the scope of the change.",
        triggers=["what does PR #N change", "describe PR #N", "show PR #N"],
        tools=["get_pr_details", "get_pr_files"],
    ),
    Skill(
        name="review_pr",
        description="Full code review: diff + files + CI, written analysis only — no automatic approve/reject",
        prompt=(
            "When asked to review a PR:\n"
            "1. Call get_pr_details, get_pr_diff, get_pr_files, and get_ci_status in sequence\n"
            "2. Analyse the diff for bugs, security issues, missing error handling, performance problems, and style issues\n"
            "3. Be specific — reference file names and line numbers\n"
            "4. Respond with a written analysis in chat only — do NOT call post_review unless the user explicitly asks to post it"
        ),
        triggers=["review PR #N", "check PR #N", "look at PR #N"],
        tools=["get_pr_details", "get_pr_diff", "get_pr_files", "get_ci_status"],
    ),
    Skill(
        name="approve_pr",
        description="Post an APPROVE review — always requires explicit user confirmation",
        prompt=(
            "Only call post_review with event=APPROVE when the user explicitly says 'approve', 'approve PR #N', or similar. "
            "Never approve as a side-effect of a review request."
        ),
        triggers=["approve PR #N", "approve it", "LGTM"],
        tools=["post_review"],
        confirmation_required=True,
        confirmation_prompt="I'd like to post an **APPROVE** review on PR #{pr_number}. Type **yes** to confirm or **no** to cancel.",
    ),
    Skill(
        name="request_changes",
        description="Post a REQUEST_CHANGES review — always requires explicit user confirmation",
        prompt=(
            "Only call post_review with event=REQUEST_CHANGES when the user explicitly asks to request changes. "
            "Never request changes as a side-effect of a review request."
        ),
        triggers=["request changes on PR #N", "reject PR #N"],
        tools=["post_review"],
        confirmation_required=True,
        confirmation_prompt="I'd like to post a **REQUEST_CHANGES** review on PR #{pr_number}. Type **yes** to confirm or **no** to cancel.",
    ),
    Skill(
        name="merge_pr",
        description="Merge a PR using squash strategy — always requires explicit user confirmation",
        prompt=(
            "Only call merge_pr when the user explicitly asks to merge. "
            "Before merging, summarise the PR title and number and ask for confirmation. "
            "Never merge without the user typing 'yes', 'go ahead', 'merge it', or similar."
        ),
        triggers=["merge PR #N", "merge it", "go ahead and merge"],
        tools=["merge_pr"],
        confirmation_required=True,
        confirmation_prompt="Ready to merge PR #{pr_number} using squash strategy. Type **yes** to confirm or **no** to cancel.",
    ),
]

# Tools that need a confirmation gate keyed by (tool_name, event) or just tool_name
CONFIRMATION_GATES: dict[tuple, Skill] = {
    ("post_review", "APPROVE"):          next(s for s in SKILLS if s.name == "approve_pr"),
    ("post_review", "REQUEST_CHANGES"):  next(s for s in SKILLS if s.name == "request_changes"),
    ("merge_pr", None):                  next(s for s in SKILLS if s.name == "merge_pr"),
}


def build_system_prompt() -> str:
    skill_block = "\n\n".join(
        f"## Skill: {s.name}\n{s.prompt}" for s in SKILLS
    )
    return f"""You are a senior software engineer and PR review agent.

You have access to a GitHub repository and can:
- List open pull requests
- Fetch PR details, diffs, and changed files
- Check CI status
- Post reviews (approve, comment, request changes)
- Merge pull requests

General rules:
- Be specific — reference file names and line numbers when pointing out issues
- Keep responses concise but complete
- Never take a destructive action (approve, request changes, merge) without explicit user confirmation

{skill_block}"""


def get_confirmation_prompt(tool_name: str, inputs: dict) -> str | None:
    event = inputs.get("event")
    skill = CONFIRMATION_GATES.get((tool_name, event)) or CONFIRMATION_GATES.get((tool_name, None))
    if skill is None:
        return None
    return skill.confirmation_prompt.format(
        pr_number=inputs.get("pr_number", "?")
    )
