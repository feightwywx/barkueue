from __future__ import annotations

import time
from queue import Empty
from threading import Thread
from typing import TYPE_CHECKING

from barkueue.event import (
    HANDLER_AFTER_RUN,
    HANDLER_BEFORE_RUN,
    TASK_AFTER_RUN,
    TASK_BEFORE_RUN,
)
from barkueue.util import _logger
from barkueue.util.exchange import match_topic

if TYPE_CHECKING:
    from barkueue.application import Application
    from barkueue.queue import DedupPriorityQueue


class Worker:
    app: Application
    running: bool = True
    queue: DedupPriorityQueue
    thread: Thread

    def __init__(self, app: Application) -> None:
        self.app = app
        self.queue = app.queue
        self.thread = Thread(target=self.loop)

    def _get_topic_handlers(self, topic: str) -> list:
        """Return all handlers whose registered pattern matches the topic."""
        return [
            handler
            for pattern, handler in self.app.executors.items()
            if match_topic(pattern, topic)
        ]

    def loop(self):
        while self.running:
            try:
                with self.queue.get_context(timeout=self.app.queue_timeout) as task:
                    self.app._fire_event(TASK_BEFORE_RUN, task=task)

                    handlers = self._get_topic_handlers(task.topic)
                    if not handlers:
                        _logger.error(
                            f"no handler for topic={task.topic}, task={task.id}"
                        )
                        task.update_status(1)
                        self.app._fire_event(TASK_AFTER_RUN, task=task)
                        continue

                    failed = False
                    for handler in handlers:
                        self.app._fire_event(
                            HANDLER_BEFORE_RUN, task=task, handler=handler
                        )
                        try:
                            handler(task)
                        except Exception:
                            _logger.exception(
                                f"Task(id={task.id}, topic={task.topic})"
                                f" failed on handler {handler.__name__}"
                            )
                            failed = True
                        self.app._fire_event(
                            HANDLER_AFTER_RUN, task=task, handler=handler
                        )

                    if failed:
                        task.update_status(1)
                    else:
                        task.update_status(0)
                    self.app._fire_event(TASK_AFTER_RUN, task=task)
            except Empty:
                continue
        
    def start(self):
        self.thread.start()

    def join(self, timeout: float | None = None):
        self.thread.join(timeout)

    def stop(self):
        self.running = False


class DataSyncWorker(Worker):
    def loop(self):
        while self.running:
            _logger.info("Fetch tasks from datasources...")
            start = time.monotonic()
            for ds in self.app.sources:
                ds.push()
                ds.fetch()
                try:
                    while task := ds.tasks.pop():
                        self.app.queue.put(task)
                except IndexError:
                    continue
            elapsed = time.monotonic() - start
            sleep_time = self.app.fetch_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
