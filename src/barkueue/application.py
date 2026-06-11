from collections.abc import Callable, Iterable, MutableSequence
from functools import wraps
from typing import TypeVar

from barkueue.datasource.type import DataSource
from barkueue.event import APP_AFTER_RUN, APP_BEFORE_RUN, TASK_AFTER_RUN, Event
from barkueue.queue import DedupPriorityQueue
from barkueue.schedule import _next_cron_time
from barkueue.task import Task
from barkueue.util import _logger
from barkueue.worker import DataSyncWorker, Worker

R = TypeVar("R")


class Application:
    sources: Iterable[DataSource]
    executors: dict[str, Callable[[Task], R]]
    worker_count: int
    workers: MutableSequence[Worker]
    queue: DedupPriorityQueue

    def __init__(
        self,
        sources: Iterable[DataSource],
        worker_count: int = 1,
        queue_timeout: float = 5,
        fetch_interval: float = 0,
    ) -> None:
        self.sources = sources
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

    def schedule(self, cron: str, task: Task) -> None:
        """Schedule a recurring task using a cron expression.

        The first occurrence is enqueued immediately with ``due`` set to the
        next cron time. After each occurrence completes, a new task with the
        same ``topic`` and ``message`` is created and enqueued for the next
        cron time.

        Args:
            cron: A standard 5-field cron expression
                (``"minute hour dom month dow"``).
            task: Template task whose ``topic`` and ``message`` are reused
                for every occurrence. The task's ``due`` and ``id`` are
                overwritten for each occurrence.

        Example::

            app.schedule("*/5 * * * *", Task("report.gen", "weekly_report"))
        """
        # Mutable container so the closure can track the latest enqueued task.
        current: list[Task] = [task]

        def _enqueue_next() -> None:
            new_task: Task = Task(task.topic, task.message)
            new_task.adapter = task.adapter
            new_task.due = _next_cron_time(cron)
            current[0] = new_task
            self.queue.put(new_task)

        # Register the event handler BEFORE enqueuing the first task.
        # Otherwise the worker could process and complete the task before
        # the handler is registered, breaking the chain.
        @self.event(TASK_AFTER_RUN)
        def _reschedule(event: Event) -> None:
            if event.task is current[0]:
                _enqueue_next()

        _enqueue_next()

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
