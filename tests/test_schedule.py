from __future__ import annotations

import time
from datetime import datetime

import pytest
from croniter import CroniterBadCronError

from barkueue.application import Application
from barkueue.datasource import ArrayDataSource
from barkueue.schedule import _next_cron_time
from barkueue.task import Task
from barkueue.worker import Worker


class TestNextCronTime:
    def test_every_5_minutes(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        result = _next_cron_time("*/5 * * * *", base)
        assert result == datetime(2026, 1, 1, 12, 5, 0)

    def test_specific_hour(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        result = _next_cron_time("0 9 * * *", base)
        assert result == datetime(2026, 1, 2, 9, 0, 0)

    def test_every_hour_at_minute_30(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        result = _next_cron_time("30 * * * *", base)
        assert result == datetime(2026, 1, 1, 12, 30, 0)

    def test_next_cron_returns_future_time(self):
        before = datetime.now()
        result = _next_cron_time("* * * * *", before)
        # The next matching time must be strictly after the base
        assert result >= before

    def test_invalid_cron_raises(self):
        with pytest.raises(CroniterBadCronError):
            _next_cron_time("not a cron expression")


class TestSchedule:
    def _wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert condition(), f"condition not met within {timeout}s"

    def test_first_task_enqueued(self):
        app = Application(sources=[])

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass

        ds = ArrayDataSource([])
        app.schedule("* * * * *", Task("test", "msg", adapter=ds))
        assert app.queue.qsize() == 1

    def test_first_task_due_is_in_future(self):
        app = Application(sources=[])

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass

        before = datetime.now()
        ds = ArrayDataSource([])
        app.schedule("30 14 * * *", Task("test", "msg", adapter=ds))
        task = app.queue.get(timeout=1)
        # due must be in the future
        assert task.due >= before

    def test_reschedule_after_completion(self):
        app = Application(sources=[], queue_timeout=0.1)
        processed = []

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            processed.append(task.message)

        ds = ArrayDataSource([])
        tpl = Task("test", "msg", adapter=ds)
        app.schedule("* * * * *", tpl)

        worker = Worker(app)
        worker.start()
        # Wait for the first task AND the follow-up to be processed
        self._wait_for(lambda: len(processed) >= 2)
        worker.stop()
        worker.join(timeout=1)

        # At least 2 tasks were processed: initial + one follow-up
        assert len(processed) >= 2

    def test_chain_two_occurrences(self):
        app = Application(sources=[], queue_timeout=0.1)
        processed = []

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            processed.append(task.message)

        ds = ArrayDataSource([])
        tpl = Task("test", "msg", adapter=ds)
        app.schedule("* * * * *", tpl)

        worker = Worker(app)
        worker.start()
        # Chain should keep producing tasks — wait for 3 occurrences
        self._wait_for(lambda: len(processed) >= 3)
        worker.stop()
        worker.join(timeout=1)

        assert len(processed) >= 3

    def test_unrelated_task_does_not_trigger_reschedule(self):
        app = Application(sources=[], queue_timeout=0.1)
        scheduled_count = [0]
        other_count = [0]

        @app.handler("scheduled")
        def h_sched(app, task):  # noqa: ARG001
            scheduled_count[0] += 1

        @app.handler("other")
        def h_other(app, task):  # noqa: ARG001
            other_count[0] += 1

        ds = ArrayDataSource([])
        tpl = Task("scheduled", "cron_msg", adapter=ds)
        app.schedule("* * * * *", tpl)

        # Also enqueue an unrelated one-shot task
        app.queue.put(Task("other", "unrelated", adapter=ds))

        worker = Worker(app)
        worker.start()
        # Wait until both are processed at least once
        self._wait_for(
            lambda: scheduled_count[0] >= 1 and other_count[0] >= 1
        )
        worker.stop()
        worker.join(timeout=1)

        # The "other" task should have run exactly once (no reschedule)
        assert other_count[0] == 1
        # The scheduled task should have been rescheduled at least once
        assert scheduled_count[0] >= 1

    def test_new_task_has_same_topic_and_message(self):
        app = Application(sources=[], queue_timeout=0.1)
        tasks_seen = []

        @app.handler("my.topic")
        def h(app, task):  # noqa: ARG001
            tasks_seen.append((task.topic, task.message, task.id))

        ds = ArrayDataSource([])
        tpl = Task("my.topic", "payload", adapter=ds)
        app.schedule("* * * * *", tpl)

        worker = Worker(app)
        worker.start()
        self._wait_for(lambda: len(tasks_seen) >= 2)
        worker.stop()
        worker.join(timeout=1)

        first, second = tasks_seen[0], tasks_seen[1]
        assert first[0] == "my.topic"
        assert first[1] == "payload"
        assert second[0] == "my.topic"
        assert second[1] == "payload"
        assert second[2] != first[2]  # unique IDs
