import os
import json
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    ChatSession,
    Content,
    Part,
    Tool,
    FunctionDeclaration,
)
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
- Keep responses concise but complete"""


def _build_gemini_tools() -> list[Tool]:
    declarations = [
        FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["parameters"],
        )
        for t in TOOLS
    ]
    return [Tool(function_declarations=declarations)]


class PRAgent:
    def __init__(self):
        vertexai.init(
            project=os.environ["GCP_PROJECT_ID"],
            location=os.environ.get("GCP_REGION", "us-central1"),
        )
        self.model = GenerativeModel(
            model_name="gemini-2.0-flash-001",
            system_instruction=SYSTEM_PROMPT,
            tools=_build_gemini_tools(),
        )
        self.repo = os.environ["GITHUB_REPO"]
        self.history: list[Content] = []
        self.pending_merge: int | None = None

    def chat(self, user_message: str) -> str:
        # Handle merge confirmation separately
        if self.pending_merge is not None:
            if user_message.strip().lower() in ("yes", "y", "go ahead", "merge it", "do it", "confirm"):
                pr_number = self.pending_merge
                self.pending_merge = None
                return self._do_merge(pr_number)
            if user_message.strip().lower() in ("no", "n", "cancel", "stop"):
                self.pending_merge = None
                return "Merge cancelled."

        self.history.append(Content(role="user", parts=[Part.from_text(user_message)]))
        response_text = self._run()
        self.history.append(Content(role="model", parts=[Part.from_text(response_text)]))
        return response_text

    def _run(self) -> str:
        messages = list(self.history)

        while True:
            response = self.model.generate_content(messages)
            candidate = response.candidates[0]
            parts = candidate.content.parts

            # Collect any text parts
            text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]

            # Check for function calls
            fn_calls = [p.function_call for p in parts if hasattr(p, "function_call") and p.function_call.name]

            if not fn_calls:
                return "\n".join(text_parts)

            # Add model turn to message history
            messages.append(candidate.content)

            # Execute each function call and collect results
            fn_results = []
            for fn_call in fn_calls:
                name = fn_call.name
                inputs = dict(fn_call.args)
                print(f"  [calling {name}({inputs})]")

                # Guard: intercept merge and ask for confirmation
                if name == "merge_pr":
                    pr_number = int(inputs.get("pr_number", 0))
                    self.pending_merge = pr_number
                    fn_results.append(
                        Part.from_function_response(
                            name=name,
                            response={"result": "Merge blocked — waiting for explicit user confirmation."},
                        )
                    )
                    # Add the function response and return early
                    messages.append(Content(role="user", parts=fn_results))
                    return f"Ready to merge PR #{pr_number} using squash strategy. Type **yes** to confirm or **no** to cancel."

                try:
                    result_str = execute_tool(name, inputs, self.repo)
                    result = json.loads(result_str) if result_str.startswith(("{", "[")) else {"result": result_str}
                except Exception as e:
                    result = {"error": str(e)}

                fn_results.append(
                    Part.from_function_response(name=name, response={"result": result})
                )

            messages.append(Content(role="user", parts=fn_results))
            # loop continues with function results fed back

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
