from barkueue.application import Application
from barkueue.task import Task


def make_app():
    return Application(sources=[])


class TestHandlerRegistration:
    def test_exact_topic_registered(self):
        app = make_app()
        called = []

        @app.handler("order.created")
        def h(app, task):  # noqa: ARG001
            called.append(task)

        assert "order.created" in app.executors
        h(Task("order.created", "msg"))
        assert len(called) == 1

    def test_wildcard_topic_registered(self):
        app = make_app()

        @app.handler("order.*")
        def h(app, task):  # noqa: ARG001
            pass

        assert "order.*" in app.executors

    def test_multiple_handlers_registered(self):
        app = make_app()

        @app.handler("a")
        def a(app, task):  # noqa: ARG001
            pass

        @app.handler("b")
        def b(app, task):  # noqa: ARG001
            pass

        assert len(app.executors) == 2
