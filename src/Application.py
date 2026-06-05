from collections.abc import Callable, Iterable, MutableSequence
from functools import wraps
from typing import TypeVar

from src.datasource.type import DataSource
from src.Queue import DedupPriorityQueue
from src.Task import Task
from src.util import _logger
from src.Worker import DataSyncWorker, Worker

QUEUE_TIMEOUT = 5

R = TypeVar("R")


class Application:
    sources: Iterable[DataSource]
    executors: dict[str, Callable[[Task], R]] = {}
    worker_count: int
    workers: MutableSequence[Worker] = []
    queue: DedupPriorityQueue

    def __init__(self, sources: Iterable[DataSource], worker_count: int = 1) -> None:
        self.sources = sources
        self.worker_count = worker_count
        self.queue = DedupPriorityQueue()

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

    def run(self) -> None:
        try:
            # create fetcher
            self.workers.append(DataSyncWorker(self, queue_timeout=QUEUE_TIMEOUT))

            for _ in range(self.worker_count):
                self.workers.append(Worker(self, queue_timeout=QUEUE_TIMEOUT))
            for worker in self.workers:
                _logger.debug(f"created worker {worker}")
                worker.start()

            for worker in self.workers:
                worker.join()

        except KeyboardInterrupt:
            _logger.info("shutting down gracefully...")
            for worker in self.workers:
                worker.stop()
