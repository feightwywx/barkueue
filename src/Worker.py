from __future__ import annotations

import time
from queue import Empty
from threading import Thread
from typing import TYPE_CHECKING

from src.util import _logger

if TYPE_CHECKING:
    from src.Application import Application
    from src.Queue import DedupPriorityQueue


class Worker:
    app: Application
    running: bool = True
    queue: DedupPriorityQueue
    thread: Thread

    def __init__(self, app: Application) -> None:
        self.app = app
        self.queue = app.queue
        self.thread = Thread(target=self.loop)

    def loop(self):
        while self.running:
            try:
                with self.queue.get_context(timeout=self.app.queue_timeout) as task:
                    handler = self.app.executors.get(task.topic)
                    if handler is None:
                        raise RuntimeError(
                            f'cannot find handler {task.topic} for {task.id}'
                        )

                    try:
                        handler(task)
                    except Exception as e:
                        _logger.error(
                            f"Task(id={task.id}, topic={task.topic}) failed: {e}"
                        )
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
