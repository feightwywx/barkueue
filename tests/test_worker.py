import pytest

from barkueue.application import Application
from barkueue.task import Task
from barkueue.worker import Worker


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
        # registration order: star first, exact second
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
            try:
                h(Task("test.msg", "msg"))
            except Exception:
                pass
        assert results == ["fail", "ok"]
