def takeover_success(metrics: dict) -> bool:
    return bool(metrics["eventual_task_success"] and metrics["handover_complete"]
                and not metrics["drop"] and not metrics["takeover_failure"])

