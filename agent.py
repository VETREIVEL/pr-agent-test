import os
import anthropic
from tools import TOOLS, execute_tool

SYSTEM_PROMPT = """You are a senior software engineer and PR review agent.

You have access to a GitHub repository and can:
- List open pull requests
- Fetch PR details, diffs, and changed files
- Check CI status
- Post reviews (approve, comment, request changes)
- Merge pull requests

Your behavior:
- When asked to review a PR, always fetch the diff and files first, then give a thorough analysis
- Look for: bugs, security issues, missing error handling, performance problems, style issues
- Be specific — reference file names and line numbers when pointing out issues
- Check CI status as part of every review
- NEVER merge without explicit user confirmation ("yes", "go ahead", "merge it")
- Before merging, always summarize what you're about to do and ask for confirmation
- Keep responses concise but complete

You are chatting interactively — the user may ask follow-up questions about the PR,
ask you to explain specific parts, or decide to merge. Stay in context across the conversation."""


class PRAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.repo = os.environ["GITHUB_REPO"]
        self.history = []
        self.pending_merge = None  # tracks if we're waiting for merge confirmation

    def chat(self, user_message: str) -> str:
        # Check for merge confirmation
        if self.pending_merge and user_message.strip().lower() in ("yes", "y", "go ahead", "merge it", "do it", "confirm"):
            pr_number = self.pending_merge
            self.pending_merge = None
            return self._do_merge(pr_number)

        if self.pending_merge and user_message.strip().lower() in ("no", "n", "cancel", "stop"):
            self.pending_merge = None
            return "Merge cancelled."

        self.history.append({"role": "user", "content": user_message})
        response = self._run(self.history)
        self.history.append({"role": "assistant", "content": response})
        return response

    def _run(self, messages: list) -> str:
        while True:
            resp = self.client.messages.create(
                model="claude-opus-4-8",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            # Collect all text from the response
            text_parts = [b.text for b in resp.content if b.type == "text"]

            if resp.stop_reason == "end_turn":
                return "\n".join(text_parts)

            if resp.stop_reason == "tool_use":
                # Add assistant turn with all content blocks
                messages = messages + [{"role": "assistant", "content": resp.content}]

                # Execute all tool calls
                tool_results = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue

                    print(f"  [calling {block.name}({block.input})]")

                    # Guard: require confirmation before merge
                    if block.name == "merge_pr":
                        pr_number = block.input.get("pr_number")
                        self.pending_merge = pr_number
                        # Return without executing — ask user to confirm
                        messages = messages + [{
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "Merge blocked — waiting for user confirmation.",
                            }]
                        }]
                        return f"Ready to merge PR #{pr_number}. Type **yes** to confirm or **no** to cancel."

                    try:
                        result = execute_tool(block.name, block.input, self.repo)
                    except Exception as e:
                        result = f"Error: {e}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                messages = messages + [{"role": "user", "content": tool_results}]
                # loop continues with tool results

    def _do_merge(self, pr_number: int) -> str:
        try:
            import github
            result = github.merge_pr(self.repo, pr_number, strategy="squash")
            if result.get("merged"):
                return f"PR #{pr_number} merged successfully. Commit SHA: `{result['sha']}`"
            else:
                return f"Merge failed: {result.get('message', 'unknown error')}"
        except Exception as e:
            return f"Merge failed: {e}"
