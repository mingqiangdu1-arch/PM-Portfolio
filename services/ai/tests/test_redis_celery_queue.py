from app.tasking.redis_celery import RedisCeleryQueue


class RedisFake:
    def __init__(self, result=True):
        self.result = result

    def ping(self):
        return self.result


class CeleryFake:
    def __init__(self):
        self.calls = []

    def send_task(self, name, **kwargs):
        self.calls.append((name, kwargs))


def test_dispatch_contains_only_identifiers_and_trace() -> None:
    celery = CeleryFake()
    queue = RedisCeleryQueue(RedisFake(), celery, queue_name="interactive")
    queue.ensure_available()
    queue.enqueue("task-1", "trace-1")
    assert celery.calls == [
        (
            "ai.execute_task",
            {
                "kwargs": {"task_public_id": "task-1", "trace_id": "trace-1"},
                "queue": "interactive",
            },
        )
    ]
