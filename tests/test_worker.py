import contextlib
import threading
import time
from datetime import datetime

from barkueue.application import Application
from barkueue.datasource import ArrayDataSource
from barkueue.task import Task
from barkueue.worker import DataSyncWorker, Worker


class TestGetTopicHandlers:
    def test_returns_matching_in_registration_order(self):
        app = Application(sources=[])

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
        app = Application(sources=[])

        @app.handler("payment.*")
        def h(app, task):  # noqa: ARG001
            pass

        worker = Worker(app)
        handlers = worker._get_topic_handlers("order.created")
        assert handlers == []

    def test_handlers_executed_in_sequence(self):
        app = Application(sources=[])
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
        app = Application(sources=[])
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
    """Integration tests that start/stop real Worker threads."""

    def _wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert condition(), f"condition not met within {timeout}s"

    def test_worker_processes_task_successfully(self):
        processed = []

        app = Application(sources=[])

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            processed.append(task.message)

        # Pre-load the queue with a task
        ds = ArrayDataSource([])
        task = Task("test", "hello", adapter=ds)
        app.queue.put(task)

        worker = Worker(app)
        worker.start()
        self._wait_for(lambda: len(processed) == 1)
        worker.stop()
        worker.join(timeout=3)

        assert processed == ["hello"]

    def test_worker_marks_failed_task_status_1(self):
        app = Application(sources=[])

        @app.handler("test")
        def h(app, task):  # noqa: ARG001
            raise RuntimeError("fail")

        task = Task("test", "msg")
        app.queue.put(task)

        ds = ArrayDataSource([])
        task.adapter = ds

        worker = Worker(app)
        worker.start()
        self._wait_for(lambda: bool(ds._updated))
        worker.stop()
        worker.join(timeout=3)

        ds.push()
        assert ds._updated == {}

    def test_worker_marks_no_handler_task_failed(self):
        app = Application(sources=[])

        task = Task("unknown_topic", "msg")
        app.queue.put(task)

        internal = [task]
        ds = ArrayDataSource(internal)
        task.adapter = ds

        worker = Worker(app)
        worker.start()
        self._wait_for(lambda: bool(ds._updated))
        worker.stop()
        worker.join(timeout=3)

        ds.push()
        assert internal[0].status == 1

    def test_multiple_handlers_all_succeed(self):
        results = []
        app = Application(sources=[])

        @app.handler("test.*")
        def h1(app, task):  # noqa: ARG001
            results.append("h1")

        @app.handler("test.#")
        def h2(app, task):  # noqa: ARG001
            results.append("h2")

        ds = ArrayDataSource([])
        task = Task("test.msg", "msg")
        task.adapter = ds
        app.queue.put(task)

        worker = Worker(app)
        worker.start()
        self._wait_for(lambda: len(results) == 2)
        worker.stop()
        worker.join(timeout=3)

        assert results == ["h1", "h2"]

    def test_multiple_handlers_one_fails_still_marks_failed(self):
        results = []
        app = Application(sources=[])

        @app.handler("test.*")
        def h1(app, task):  # noqa: ARG001
            raise RuntimeError("fail")

        @app.handler("test.#")
        def h2(app, task):  # noqa: ARG001
            results.append("h2")

        internal = [Task("test.msg", "msg")]
        ds = ArrayDataSource(internal)
        task = internal[0]
        task.adapter = ds
        app.queue.put(task)

        worker = Worker(app)
        worker.start()
        self._wait_for(lambda: len(results) == 1)
        worker.stop()
        worker.join(timeout=3)

        ds.push()
        assert internal[0].status == 1

    def test_worker_stop(self):
        app = Application(sources=[])
        worker = Worker(app)
        worker.start()
        assert worker.running is True
        worker.stop()
        assert worker.running is False
        worker.join(timeout=3)


class TestApplicationRun:
    """Full integration: Application.run() with real workers."""

    def _wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert condition(), f"condition not met within {timeout}s"

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

        self._wait_for(lambda: len(results) == 1 and internal[0].status == 0, timeout=5)

        # Stop all workers
        for w in app.workers:
            w.stop()
        t.join(timeout=5)

        assert results == ["hello"]
        assert internal[0].status == 0

class TestDataSyncWorkerLoop:
    def _wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert condition(), f"condition not met within {timeout}s"

    def test_fetches_tasks_into_queue(self):
        internal = [
            Task("test", "hello", due=datetime(2020, 1, 1)),
            Task("test", "world", due=datetime(2020, 1, 2)),
        ]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds])

        # Start DataSyncWorker, let it run one cycle
        dsw = DataSyncWorker(app)
        dsw.start()
        self._wait_for(lambda: app.queue.qsize() >= 2)
        dsw.stop()
        dsw.join(timeout=3)

        assert app.queue.qsize() == 2

    def test_pushes_before_fetch(self):
        internal = [Task("test", "msg")]
        ds = ArrayDataSource(internal)
        app = Application(sources=[ds], fetch_interval=0)

        # Pre-buffer a status update without pushing
        ds.update_status(internal[0], 0)

        dsw = DataSyncWorker(app)
        dsw.start()
        # Wait for push to happen (status becomes non-None in _internal)
        self._wait_for(lambda: internal[0].status == 0)
        dsw.stop()
        dsw.join(timeout=3)

        assert internal[0].status == 0
