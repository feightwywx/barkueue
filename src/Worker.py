from __future__ import annotations

from queue import Empty
from threading import Thread
from typing import TYPE_CHECKING

from src.Task import Task
from src.util import _logger

if TYPE_CHECKING:
    from queue import PriorityQueue

    from src.Application import Application


class Worker:
    app: Application
    running: bool = True
    queue: PriorityQueue[Task]
    queue_timeout: float | None
    thread: Thread

    def __init__(
            self,
            app: Application,
            queue_timeout: float | None = None
        ) -> None:
        self.app = app
        self.queue = app.queue
        self.queue_timeout = queue_timeout
        self.thread = Thread(target=self.loop)

    def loop(self):
        while self.running:
            try:
                task = self.queue.get(timeout=self.queue_timeout)
            except Empty:
                continue

            handler = self.app.executors.get(task.topic)
            if handler is None:
                raise RuntimeError(f'cannot find handler {task.topic} for {task.id}')
            
            try:
                handler(task)
            except Exception as e:
                _logger.error(f"Task(id={task.id}, topic={task.topic}) failed: {e}")
                try:
                    task.update_status(1)
                except Exception as ue:
                    _logger.error(f"Failed to update status for task {task.id}: {ue}")
            else:
                try:
                    task.update_status(0)
                except Exception as ue:
                    _logger.error(f"Failed to update status for task {task.id}: {ue}")
        
    def start(self):
        self.thread.start()

    def join(self):
        self.thread.join()

    def stop(self):
        self.running = False


class DataSyncWorker(Worker):
    def loop(self):
        while self.running:
            for ds in self.app.sources:
                ds.fetch()
                try:
                    while task := ds.tasks.pop():
                        self.app.enqueue(task)
                except IndexError:
                    continue
