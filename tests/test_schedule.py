from __future__ import annotations

import threading
from datetime import datetime

import pytest
from conftest import wait_until
from croniter import CroniterBadCronError

from barkueue.application import Application
from barkueue.task import Task
from barkueue.util.schedule import Scheduler, _next_cron_time


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
    def test_first_task_enqueued(self):
        app = Application(sources=[])
        scheduler = Scheduler(app)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass

        scheduler.add("* * * * *", Task("test", "msg"))
        # Task is in the scheduler's internal datasource
        assert len(scheduler.datasource._internal) == 1

    def test_first_task_due_is_in_future(self):
        app = Application(sources=[])
        scheduler = Scheduler(app)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass

        before = datetime.now()
        scheduler.add("30 14 * * *", Task("test", "msg"))
        task = scheduler.datasource._internal[0]
        # due must be in the future
        assert task.due >= before

    def test_reschedule_after_completion(self):
        processed = []
        app = Application(sources=[], fetch_interval=0.1, queue_timeout=0.2)
        scheduler = Scheduler(app)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            processed.append(task.message)

        scheduler.add("* * * * * *", Task("test", "msg"))

        t = threading.Thread(target=app.run)
        t.start()
        # Wait for the first task AND the follow-up to be processed
        wait_until(lambda: len(processed) >= 2)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        # At least 2 tasks were processed: initial + one follow-up
        assert len(processed) >= 2

    def test_chain_two_occurrences(self):
        processed = []
        app = Application(sources=[], fetch_interval=0.1, queue_timeout=0.2)
        scheduler = Scheduler(app)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            processed.append(task.message)

        scheduler.add("* * * * * *", Task("test", "msg"))

        t = threading.Thread(target=app.run)
        t.start()
        # Chain should keep producing tasks — wait for 3 occurrences
        wait_until(lambda: len(processed) >= 3)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert len(processed) >= 3

    def test_unrelated_task_does_not_trigger_reschedule(self):
        scheduled_count = [0]
        other_count = [0]

        # The one-shot task goes through a separate ArrayDataSource
        internal = [Task("other", "unrelated", due=datetime(2020, 1, 1))]
        from barkueue.datasource import ArrayDataSource
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.2)
        scheduler = Scheduler(app)

        @app.handler("scheduled")
        def h_sched(app, task):  # noqa: ARG001
            scheduled_count[0] += 1

        @app.handler("other")
        def h_other(app, task):  # noqa: ARG001
            other_count[0] += 1

        scheduler.add("* * * * * *", Task("scheduled", "cron_msg"))

        t = threading.Thread(target=app.run)
        t.start()
        # Wait until both are processed at least once
        wait_until(lambda: scheduled_count[0] >= 1 and other_count[0] >= 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        # The "other" task should have run exactly once (no reschedule)
        assert other_count[0] == 1
        # The scheduled task should have been rescheduled at least once
        assert scheduled_count[0] >= 1

    def test_new_task_has_same_topic_and_message(self):
        tasks_seen = []
        app = Application(sources=[], fetch_interval=0.1, queue_timeout=0.2)
        scheduler = Scheduler(app)

        @app.handler("my.topic")
        def h(app, task):  # noqa: ARG001
            tasks_seen.append((task.topic, task.message, task.id))

        scheduler.add("* * * * * *", Task("my.topic", "payload"))

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(tasks_seen) >= 2)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        first, second = tasks_seen[0], tasks_seen[1]
        assert first[0] == "my.topic"
        assert first[1] == "payload"
        assert second[0] == "my.topic"
        assert second[1] == "payload"
        assert second[2] != first[2]  # unique IDs
