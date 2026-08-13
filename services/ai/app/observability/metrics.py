"""Low-cardinality AI runtime metrics."""

from prometheus_client import Counter, Gauge, Histogram

AI_TASKS_TOTAL = Counter(
    "ai_tasks_total",
    "AI task state outcomes.",
    ("task_type", "status", "reason_class"),
)
AI_CALLS_TOTAL = Counter(
    "ai_calls_total",
    "AI provider call outcomes.",
    ("provider", "model", "outcome", "error_class"),
)
AI_CALL_DURATION_SECONDS = Histogram(
    "ai_call_duration_seconds",
    "AI provider call duration.",
    ("provider", "model"),
)
AI_TOKENS_TOTAL = Counter(
    "ai_tokens_total",
    "AI token usage when the provider reports it.",
    ("provider", "model", "direction"),
)
AI_COST_TOTAL = Counter(
    "ai_cost_total",
    "Reported or deterministically calculated AI cost.",
    ("provider", "model", "currency", "cost_source"),
)
AI_QUEUE_ACCEPTING = Gauge(
    "ai_queue_accepting",
    "Whether the service is accepting new queued tasks.",
)
EVENT_QUALITY_FAILURES_TOTAL = Counter(
    "ai_event_quality_failures_total",
    "Event quality failures by stable class.",
    ("failure_class",),
)
