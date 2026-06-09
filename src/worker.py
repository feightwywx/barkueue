from __future__ import annotations

import time
from queue import Empty
from threading import Thread
from typing import TYPE_CHECKING

from src.util import _logger
from src.util.exchange import match_topic

if TYPE_CHECKING:
    from src.application import Application
    from src.queue import DedupPriorityQueue


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
                    handlers = self._get_topic_handlers(task.topic)
                    if not handlers:
                        _logger.error(
                            f"no handler for topic={task.topic}, task={task.id}"
                        )
                        task.update_status(1)
                        continue

                    failed = False
                    for handler in handlers:
                        try:
                            handler(task)
                        except Exception:
                            _logger.exception(
                                f"Task(id={task.id}, topic={task.topic})"
                                f" failed on handler {handler.__name__}"
                            )
                            failed = True

                    if failed:
                        try:
                            task.update_status(1)
                        except Exception as ue:
                            _logger.error(
                                f"Failed to update status for task {task.id}: {ue}"
                            )
                    else:
                        try:
                            task.update_status(0)
                        except Exception as ue:
                            _logger.error(
                                f"Failed to update status for task {task.id}: {ue}"
                            )
            except Empty:
                continue
        
    def start(self):
        self.thread.start()

    def join(self):
        self.thread.join()

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
