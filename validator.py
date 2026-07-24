def validate_pr_number(pr_number) -> int:
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError(f"Invalid PR number: {pr_number}")
    return pr_number

def validate_review_event(event: str) -> str:
    allowed = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}
    if event not in allowed:
        raise ValueError(f"Invalid review event: {event}. Must be one of {allowed}")
    return event
