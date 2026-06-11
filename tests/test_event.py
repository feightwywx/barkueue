from __future__ import annotations

import threading
from datetime import datetime

from conftest import wait_until

from barkueue.application import Application
from barkueue.datasource import ArrayDataSource
from barkueue.event import (
    APP_AFTER_RUN,
    APP_BEFORE_RUN,
    HANDLER_AFTER_RUN,
    HANDLER_BEFORE_RUN,
    TASK_AFTER_RUN,
    TASK_BEFORE_RUN,
    Event,
)
from barkueue.task import Task


class TestEventDataclass:
    def test_creates_with_app_only(self):
        app = Application(sources=[])
        event = Event(app=app)
        assert event.app is app
        assert event.task is None
        assert event.handler is None

    def test_creates_with_all_fields(self):
        app = Application(sources=[])

        def dummy():
            pass

        task = Task("test", "msg")
        event = Event(app=app, task=task, handler=dummy)
        assert event.app is app
        assert event.task is task
        assert event.handler is dummy


class TestEventRegistration:
    def test_register_single_handler(self):
        app = Application(sources=[])
        calls = []

        @app.event(APP_BEFORE_RUN)
        def on_before(event):
            calls.append(event)

        assert APP_BEFORE_RUN in app.events
        assert len(app.events[APP_BEFORE_RUN]) == 1

        app._fire_event(APP_BEFORE_RUN)
        assert len(calls) == 1
        assert calls[0].app is app

    def test_register_multiple_handlers_order_preserved(self):
        app = Application(sources=[])
        order = []

        @app.event(APP_BEFORE_RUN)
        def first(event):  # noqa: ARG001
            order.append("first")

        @app.event(APP_BEFORE_RUN)
        def second(event):  # noqa: ARG001
            order.append("second")

        app._fire_event(APP_BEFORE_RUN)
        assert order == ["first", "second"]

    def test_different_events_isolated(self):
        app = Application(sources=[])
        calls_a = []
        calls_b = []

        @app.event(APP_BEFORE_RUN)
        def on_a(event):  # noqa: ARG001
            calls_a.append(1)

        @app.event(APP_AFTER_RUN)
        def on_b(event):  # noqa: ARG001
            calls_b.append(1)

        app._fire_event(APP_BEFORE_RUN)
        assert len(calls_a) == 1
        assert len(calls_b) == 0

    def test_event_decorator_returns_original_function(self):
        app = Application(sources=[])

        @app.event(APP_BEFORE_RUN)
        def my_handler(event):  # noqa: ARG001
            pass

        # The decorated function should still be callable directly
        assert callable(my_handler)


class TestEventFiring:
    def test_fire_event_passes_event_with_correct_fields(self):
        app = Application(sources=[])
        received = []

        @app.event(TASK_BEFORE_RUN)
        def on_task(event):
            received.append(event)

        task = Task("test", "msg")
        app._fire_event(TASK_BEFORE_RUN, task=task)
        assert len(received) == 1
        assert received[0].app is app
        assert received[0].task is task
        assert received[0].handler is None

    def test_fire_event_passes_handler_field(self):
        app = Application(sources=[])
        received = []

        def dummy_handler(task):  # noqa: ARG001
            pass

        @app.event(HANDLER_BEFORE_RUN)
        def on_handler(event):
            received.append(event)

        task = Task("test", "msg")
        app._fire_event(HANDLER_BEFORE_RUN, task=task, handler=dummy_handler)
        assert len(received) == 1
        assert received[0].handler is dummy_handler

    def test_nonexistent_event_name_is_noop(self):
        app = Application(sources=[])
        # Should not raise
        app._fire_event("nonexistent_event")

    def test_event_handler_exception_logged_not_raised(self):
        app = Application(sources=[])
        second_called = []

        @app.event(APP_BEFORE_RUN)
        def failing(event):  # noqa: ARG001
            raise RuntimeError("event handler error")

        @app.event(APP_BEFORE_RUN)
        def ok(event):  # noqa: ARG001
            second_called.append(True)

        # Should not raise
        app._fire_event(APP_BEFORE_RUN)
        assert len(second_called) == 1


class TestLifecycleOrder:
    """Verify the six events fire in the correct sequence."""

    def test_event_firing_order_in_worker_loop(self):
        internal = [Task("test", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)
        events = []

        @app.event(APP_BEFORE_RUN)
        def on_app_before(event):
            events.append(("app_before", None))

        @app.event(APP_AFTER_RUN)
        def on_app_after(event):
            events.append(("app_after", None))

        @app.event(TASK_BEFORE_RUN)
        def on_task_before(event):
            events.append(("task_before", event.task))

        @app.event(HANDLER_BEFORE_RUN)
        def on_handler_before(event):
            events.append(("handler_before", event.handler))

        @app.event(HANDLER_AFTER_RUN)
        def on_handler_after(event):
            events.append(("handler_after", event.handler))

        @app.event(TASK_AFTER_RUN)
        def on_task_after(event):
            events.append(("task_after", event.task))

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: any(e[0] == "task_after" for e in events))
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        # Verify order within the worker loop (exclude app_before/app_after
        # which fire around app.run(), not inside the worker loop)
        event_names = [e[0] for e in events]
        worker_event_order = [
            n for n in event_names if n not in ("app_before", "app_after")
        ]
        assert worker_event_order == [
            "task_before",
            "handler_before",
            "handler_after",
            "task_after",
        ]


class TestHandlerEventsOnlyWhenHandlersMatch:
    def test_handler_events_not_fired_when_no_handlers_match(self):
        internal = [Task("no_match_topic", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        handler_events = []
        task_after_fired = []

        @app.event(HANDLER_BEFORE_RUN)
        def on_before(event):
            handler_events.append("before")

        @app.event(HANDLER_AFTER_RUN)
        def on_after(event):
            handler_events.append("after")

        @app.event(TASK_AFTER_RUN)
        def on_task_after(event):
            task_after_fired.append(True)

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(task_after_fired) >= 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert handler_events == []


class TestHandlerAfterRunOnException:
    def test_handler_after_run_fires_when_handler_raises(self):
        internal = [Task("test", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        after_events = []

        @app.event(HANDLER_AFTER_RUN)
        def on_after(event):
            after_events.append(event.handler)

        @app.handler("test")
        def failing(app, task):  # noqa: ARG001
            raise RuntimeError("handler failed")

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(after_events) >= 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert len(after_events) == 1
        # original function name via @wraps
        assert after_events[0].__name__ == "failing"


class TestTaskAfterRun:
    def test_task_after_run_fires_when_no_handler_matches(self):
        internal = [Task("no_match_topic", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        after_events = []

        @app.event(TASK_AFTER_RUN)
        def on_after(event):
            after_events.append(event.task)

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(after_events) >= 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert len(after_events) == 1
        assert after_events[0].topic == "no_match_topic"
        assert after_events[0].message == "msg"

    def test_task_after_run_fires_on_success(self):
        internal = [Task("test", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        after_events = []

        @app.event(TASK_AFTER_RUN)
        def on_after(event):
            after_events.append(event.task)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass

        t = threading.Thread(target=app.run)
        t.start()
        # Wait for status to be persisted (push happens after event fires)
        wait_until(lambda: internal[0].status is not None and len(after_events) >= 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert len(after_events) == 1
        assert after_events[0].topic == "test"
        assert after_events[0].message == "msg"
        assert internal[0].status == 0

    def test_task_after_run_fires_on_failure(self):
        internal = [Task("test", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        after_events = []

        @app.event(TASK_AFTER_RUN)
        def on_after(event):
            after_events.append(event.task)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            raise RuntimeError("fail")

        t = threading.Thread(target=app.run)
        t.start()
        # Wait for status to be persisted (push happens after event fires)
        wait_until(lambda: internal[0].status is not None and len(after_events) >= 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert len(after_events) == 1
        assert after_events[0].topic == "test"
        assert after_events[0].message == "msg"
        assert internal[0].status == 1

    def test_task_before_run_fires(self):
        internal = [Task("test", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        before_events = []

        @app.event(TASK_BEFORE_RUN)
        def on_before(event):
            before_events.append(event.task)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(before_events) >= 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert len(before_events) == 1
        assert before_events[0].topic == "test"
        assert before_events[0].message == "msg"


class TestAppLifecycleEvents:
    def test_app_before_run_fires_before_workers_start(self):
        app = Application(sources=[], fetch_interval=0.1, queue_timeout=0.1)
        before_fired = []
        after_fired = []

        @app.event(APP_BEFORE_RUN)
        def on_before(event):
            before_fired.append(True)
            # At this point, no workers have been created yet
            assert len(event.app.workers) == 0

        @app.event(APP_AFTER_RUN)
        def on_after(event):
            after_fired.append(True)

        # Run app in background, stop after workers are running
        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(app.workers) > 0)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert len(before_fired) == 1
        assert len(after_fired) == 1
