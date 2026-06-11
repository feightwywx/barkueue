from collections.abc import Callable, MutableSequence
from functools import wraps
from typing import TypeVar

from barkueue.datasource.type import DataSource
from barkueue.event import APP_AFTER_RUN, APP_BEFORE_RUN, Event
from barkueue.queue import DedupPriorityQueue
from barkueue.task import Task
from barkueue.util import _logger
from barkueue.worker import DataSyncWorker, Worker

R = TypeVar("R")


class Application:
    sources: MutableSequence[DataSource]
    executors: dict[str, Callable[[Task], R]]
    worker_count: int
    workers: MutableSequence[Worker]
    queue: DedupPriorityQueue

    def __init__(
        self,
        sources: MutableSequence[DataSource],
        worker_count: int = 1,
        queue_timeout: float = 1,
        fetch_interval: float = 0,
    ) -> None:
        self.sources = list(sources)
        self.executors = {}
        self.events: dict[str, list[Callable[[Event], None]]] = {}
        self.workers = []
        self.worker_count = worker_count
        self.queue = DedupPriorityQueue()
        self.queue_timeout = queue_timeout
        self.fetch_interval = fetch_interval

    def handler(self, id: str):
        """
        Decorate a function as task handler to application.

        Params:
            id (str): Handler identifier for this task type.

        Returns:
            decorator: Function decorator that auto-injects Application instance.

        Example:
            ```
            @app.handler("email_task")
            def handle_email(self: Application, task: Task) -> dict:
                # Use self.session_maker, self.engine, etc.
                with self.session_maker() as session:
                    result = process_email(task.data)
                    return {"status": "success", "result": result}

            # Later, when processing tasks:
            task = Task("email_123", {"to": "user@example.com"})
            result = handle_email(task)  # self is auto-injected
            ```
        """

        def dec(func: Callable[["Application", Task], R]) -> Callable[[Task], R]:
            @wraps(func)
            def wrapper(task):
                return func(self, task)

            self.executors[id] = wrapper
            return wrapper

        return dec

    def _fire_event(
        self,
        name: str,
        task: Task | None = None,
        handler: Callable | None = None,
    ) -> None:
        """Fire all registered handlers for an event, in registration order.

        Exceptions from event handlers are logged but do NOT propagate.
        """
        event = Event(app=self, task=task, handler=handler)
        for fn in self.events.get(name, []):
            try:
                fn(event)
            except Exception:
                _logger.exception(
                    f"Event handler {fn.__name__!r} raised an exception "
                    f"for event {name!r}"
                )

    def event(self, name: str):
        """Decorate a function as an event handler.

        Args:
            name: Event name constant, e.g. ``APP_BEFORE_RUN``.

        Example::

            @app.event(bark.APP_BEFORE_RUN)
            def on_setup(event: Event):
                ...
        """

        def dec(func: Callable[[Event], None]) -> Callable[[Event], None]:
            self.events.setdefault(name, []).append(func)
            return func

        return dec

    def run(self) -> None:
        self._fire_event(APP_BEFORE_RUN)
        try:
            # create fetcher
            self.workers.append(DataSyncWorker(self))

            for _ in range(self.worker_count):
                self.workers.append(Worker(self))
            for worker in self.workers:
                _logger.debug(f"created worker {worker}")
                worker.start()

            for worker in self.workers:
                worker.join()

        except KeyboardInterrupt:
            _logger.info("shutting down gracefully...")
            for worker in self.workers:
                worker.stop()
            for worker in self.workers:
                worker.join(timeout=self.queue_timeout)
        self._fire_event(APP_AFTER_RUN)
