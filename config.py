import os

def get_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set")
    return token

def get_github_repo() -> str:
    repo = os.environ.get("GITHUB_REPO", "")
    if not repo:
        raise ValueError("GITHUB_REPO environment variable is not set")
    return repo

def get_gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
