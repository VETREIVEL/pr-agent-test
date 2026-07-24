from __future__ import annotations

import os
import json
import re
from google import genai
from google.genai import types
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


def _build_tools() -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["parameters"],
        )
        for t in TOOLS
    ]
    return [types.Tool(function_declarations=declarations)]


class PRAgent:
    def __init__(self):
        self.client = genai.Client(
            vertexai=True,
            project=os.environ["GCP_PROJECT_ID"],
            location=os.environ.get("GCP_REGION", "us-central1"),
        )
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.tools = _build_tools()
        self.repo = os.environ["GITHUB_REPO"]
        self.history: list[types.Content] = []
        self.pending_merge: int | None = None

    def chat(self, user_message: str) -> str:
        if self.pending_merge is not None:
            if user_message.strip().lower() in ("yes", "y", "go ahead", "merge it", "do it", "confirm"):
                pr_number = self.pending_merge
                self.pending_merge = None
                return self._do_merge(pr_number)
            if user_message.strip().lower() in ("no", "n", "cancel", "stop"):
                self.pending_merge = None
                return "Merge cancelled."

        self.history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))
        response_text = self._run()
        self.history.append(types.Content(role="model", parts=[types.Part.from_text(text=response_text)]))
        return response_text

    def _run(self) -> str:
        messages = list(self.history)
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=self.tools,
        )

        while True:
            response = self.client.models.generate_content(
                model=self.model,
                contents=messages,
                config=config,
            )
            candidate = response.candidates[0]
            parts = candidate.content.parts

            text_parts = [p.text for p in parts if hasattr(p, "text") and p.text]
            fn_calls = [p.function_call for p in parts if hasattr(p, "function_call") and p.function_call and p.function_call.name]

            if not fn_calls:
                return "\n".join(text_parts)

            messages.append(candidate.content)

            fn_results = []
            for fn_call in fn_calls:
                name = fn_call.name
                inputs = dict(fn_call.args)
                print(f"  [calling {name}({inputs})]")

                if name == "merge_pr":
                    pr_number = int(inputs.get("pr_number", 0))
                    self.pending_merge = pr_number
                    fn_results.append(
                        types.Part.from_function_response(
                            name=name,
                            response={"result": "Merge blocked — waiting for explicit user confirmation."},
                        )
                    )
                    messages.append(types.Content(role="user", parts=fn_results))
                    return f"Ready to merge PR #{pr_number} using squash strategy. Type **yes** to confirm or **no** to cancel."

                try:
                    result_str = execute_tool(name, inputs, self.repo)
                    result = json.loads(result_str) if result_str.startswith(("{", "[")) else {"result": result_str}
                except Exception as e:
                    result = {"error": str(e)}

                fn_results.append(
                    types.Part.from_function_response(name=name, response={"result": result})
                )

            messages.append(types.Content(role="user", parts=fn_results))

    def auto_review(self, pr_number: int) -> dict:
        """Fetch PR diff+files, call LLM, return structured review dict."""
        import github as gh

        details = gh.get_pr_details(self.repo, pr_number)
        diff = gh.get_pr_diff(self.repo, pr_number)
        files = gh.get_pr_files(self.repo, pr_number)

        prompt = f"""Review this pull request and respond with ONLY a JSON object — no markdown, no prose outside the JSON.

PR #{pr_number}: {details['title']}
Author: {details['author']}
Base: {details['base']} ← {details['head']}
Changed files: {details['changed_files']} (+{details['additions']} -{details['deletions']})

Description:
{details['body'] or '(none)'}

Files changed:
{json.dumps(files, indent=2)}

Diff:
{diff[:12000]}

Return exactly this shape:
{{
  "summary": "<overall review summary>",
  "event": "<APPROVE | REQUEST_CHANGES | COMMENT>",
  "inline_comments": [
    {{"path": "<file path>", "line": <line number>, "body": "<comment>"}}
  ]
}}

Rules:
- event=APPROVE only if the code looks correct and safe to merge
- event=REQUEST_CHANGES if there are bugs, security issues, or missing error handling
- event=COMMENT for general feedback without a verdict
- inline_comments should reference exact file paths and line numbers from the diff
- Keep inline_comments focused: bugs, security, missing null-checks, performance hotspots"""

        config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=config,
        )
        raw = response.candidates[0].content.parts[0].text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        return json.loads(raw)

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
