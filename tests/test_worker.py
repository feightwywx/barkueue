import contextlib
import threading
from datetime import datetime

from conftest import wait_until

from barkueue.application import Application
from barkueue.datasource import ArrayDataSource
from barkueue.task import Task
from barkueue.worker import Worker


class TestGetTopicHandlers:
    def test_returns_matching_in_registration_order(self):
        app = Application(sources=[], queue_timeout=0.1)

        @app.handler("order.*")
        def star(app, task):  # noqa: ARG001
            pass

        @app.handler("order.created")
        def exact(app, task):  # noqa: ARG001
            pass

        worker = Worker(app)
        handlers = worker._get_topic_handlers("order.created")
        assert len(handlers) == 2
        assert handlers[0] is star
        assert handlers[1] is exact

    def test_returns_empty_when_no_match(self):
        app = Application(sources=[], queue_timeout=0.1)

        @app.handler("payment.*")
        def h(app, task):  # noqa: ARG001
            pass

        worker = Worker(app)
        handlers = worker._get_topic_handlers("order.created")
        assert handlers == []

    def test_handlers_executed_in_sequence(self):
        app = Application(sources=[], queue_timeout=0.1)
        results = []

        @app.handler("test.*")
        def first(app, task):  # noqa: ARG001
            results.append("first")

        @app.handler("test.#")
        def second(app, task):  # noqa: ARG001
            results.append("second")

        worker = Worker(app)
        handlers = worker._get_topic_handlers("test.msg")
        for h in handlers:
            h(Task("test.msg", "msg"))
        assert results == ["first", "second"]

    def test_one_handler_fails_others_still_run(self):
        app = Application(sources=[], queue_timeout=0.1)
        results = []

        @app.handler("test.*")
        def failing(app, task):  # noqa: ARG001
            results.append("fail")
            raise ValueError("boom")

        @app.handler("test.#")
        def ok(app, task):  # noqa: ARG001
            results.append("ok")

        worker = Worker(app)
        handlers = worker._get_topic_handlers("test.msg")
        for h in handlers:
            with contextlib.suppress(Exception):
                h(Task("test.msg", "msg"))
        assert results == ["fail", "ok"]


class TestWorkerLoop:
    """Integration tests that exercise the full Application.run() pipeline."""

    def test_worker_processes_task_successfully(self):
        results = []
        internal = [Task("test", "hello", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            results.append(task.message)

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(results) == 1)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert results == ["hello"]

    def test_worker_marks_failed_task_status_1(self):
        internal = [Task("test", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            raise RuntimeError("fail")

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: internal[0].status is not None)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert internal[0].status == 1

    def test_worker_marks_no_handler_task_failed(self):
        internal = [Task("unknown_topic", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)
        # No handlers registered — task should be marked failed

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: internal[0].status is not None)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert internal[0].status == 1

    def test_multiple_handlers_all_succeed(self):
        results = []
        internal = [Task("test.msg", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        @app.handler("test.*")
        def h1(app, task):  # noqa: ARG001
            results.append("h1")

        @app.handler("test.#")
        def h2(app, task):  # noqa: ARG001
            results.append("h2")

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(results) == 2)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert results == ["h1", "h2"]

    def test_multiple_handlers_one_fails_still_marks_failed(self):
        results = []
        internal = [Task("test.msg", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        @app.handler("test.*")
        def h1(app, task):  # noqa: ARG001
            raise RuntimeError("fail")

        @app.handler("test.#")
        def h2(app, task):  # noqa: ARG001
            results.append("h2")

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: len(results) == 1 and internal[0].status is not None)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert results == ["h2"]
        assert internal[0].status == 1

    def test_worker_stop(self):
        app = Application(sources=[], queue_timeout=0.1)
        worker = Worker(app)
        worker.start()
        assert worker.running is True
        worker.stop()
        assert worker.running is False
        worker.join(timeout=3)


class TestApplicationRun:
    """Full integration: Application.run() with real workers."""

    def test_run_processes_tasks(self):
        internal = [Task("test.msg", "hello", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=1)

        results = []

        @app.handler("test.#")
        def h(app, task):  # noqa: ARG001
            results.append(task.message)

        # Run app in a background thread
        t = threading.Thread(target=app.run)
        t.start()

        wait_until(lambda: len(results) == 1 and internal[0].status == 0, timeout=5)

        # Stop all workers
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert results == ["hello"]
        assert internal[0].status == 0

class TestDataSyncWorkerLoop:
    """Integration tests for fetch and push cycles via Application.run()."""

    def test_fetches_tasks_into_queue(self):
        results = []
        internal = [
            Task("test", "hello", due=datetime(2020, 1, 1)),
            Task("test", "world", due=datetime(2020, 1, 2)),
        ]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            results.append(task.message)

        t = threading.Thread(target=app.run)
        t.start()
        # Wait for both tasks to be processed AND their status pushed
        wait_until(lambda: all(t.status is not None for t in internal))
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert sorted(results) == sorted(["hello", "world"])
        assert all(t.status == 0 for t in internal)

    def test_pushes_before_fetch(self):
        internal = [Task("test", "msg", due=datetime(2020, 1, 1))]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0.1, queue_timeout=0.5)

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            pass  # handler succeeds, status becomes 0

        t = threading.Thread(target=app.run)
        t.start()
        wait_until(lambda: internal[0].status is not None)
        for w in app.workers:
            w.stop()
        t.join(timeout=2)

        assert internal[0].status == 0
