"""Business-facing progress states derived only from persisted execution and results."""


def result_state(status, workflow, *, latest_status=None, published=False, stale=False,
                 verification_unavailable=False, scope_clarification=False):
    from .business_decisions import BUSY

    if status in BUSY:
        return "processing"
    if status == "NEEDS_CLARIFICATION" or scope_clarification:
        return "clarification"
    if stale:
        return "needs_reassessment"
    if status == "CANCELLED":
        return "cancelled"
    if verification_unavailable:
        return "verification_unavailable"
    if status == "ERROR":
        return "interrupted"
    if latest_status == "PARTIAL":
        return "partial"
    if latest_status == "READY":
        if published:
            return "published"
        return "draft_ready" if workflow == "request" else "completed"
    return "saved"
