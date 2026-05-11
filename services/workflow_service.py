def requires_reason(status: str) -> bool:
    return status in ["Rejected", "Fixed"]


def next_step(status: str) -> str | None:
    if status == "Rejected":
        return "waiting_reject_reason"
    if status == "Fixed":
        return "waiting_fixed_reason"
    if status == "Assigned":
        return "waiting_assignment_name"
    return None