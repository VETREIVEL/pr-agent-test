import os
import json
import re
from google import genai
from google.genai import types
from tools import TOOLS, execute_tool
from skills import build_system_prompt, get_confirmation_prompt


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
        self.pending_confirmation: dict | None = None  # {"tool": str, "inputs": dict}

    def chat(self, user_message: str) -> str:
        confirmed = user_message.strip().lower() in ("yes", "y", "go ahead", "merge it", "do it", "confirm")
        cancelled = user_message.strip().lower() in ("no", "n", "cancel", "stop")

        if self.pending_confirmation is not None:
            if confirmed:
                pending = self.pending_confirmation
                self.pending_confirmation = None
                return self._execute_confirmed(pending["tool"], pending["inputs"])
            if cancelled:
                self.pending_confirmation = None
                return "Cancelled."

        self.history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))
        response_text = self._run()
        self.history.append(types.Content(role="model", parts=[types.Part.from_text(text=response_text)]))
        return response_text

    def _run(self) -> str:
        messages = list(self.history)
        config = types.GenerateContentConfig(
            system_instruction=build_system_prompt(),
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

                confirmation_prompt = get_confirmation_prompt(name, inputs)
                if confirmation_prompt:
                    self.pending_confirmation = {"tool": name, "inputs": inputs}
                    fn_results.append(
                        types.Part.from_function_response(
                            name=name,
                            response={"result": "Blocked — waiting for explicit user confirmation."},
                        )
                    )
                    messages.append(types.Content(role="user", parts=fn_results))
                    return confirmation_prompt

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

        config = types.GenerateContentConfig(system_instruction=build_system_prompt())
        response = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=config,
        )
        raw = response.candidates[0].content.parts[0].text.strip()

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

    def _execute_confirmed(self, tool: str, inputs: dict) -> str:
        try:
            result_str = execute_tool(tool, inputs, self.repo)
            result = json.loads(result_str) if result_str.startswith(("{", "[")) else {"result": result_str}
            if tool == "merge_pr":
                if result.get("result", {}).get("merged"):
                    return f"PR #{inputs['pr_number']} merged. Commit SHA: `{result['result']['sha']}`"
                return f"Merge failed: {result.get('result', {}).get('message', result)}"
            if tool == "post_review":
                r = result.get("result", {})
                return f"Review posted (id: {r.get('id')}, state: {r.get('state')})"
            return json.dumps(result)
        except Exception as e:
            return f"Failed: {e}"
