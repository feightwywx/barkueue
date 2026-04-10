from queue import Empty
from threading import Thread
from typing import TYPE_CHECKING

from src.Task import Task

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

    def loop(self):
        while self.running:
            try:
                task = self.queue.get(timeout=self.queue_timeout)
            except Empty:
                continue

            handler = self.app.executors.get(task.id)
            if handler is None:
                raise RuntimeError(f'cannot find handler {task.topic} for {task.id}:')
            
            try:
                handler(task)
            except Exception as e:
                print(e)
                task.update_status(1)
            else:
                task.update_status(0)
        
    def start(self):
        thread = Thread(target=self.loop)
        thread.start()

    def join(self):
        self.thread.join()

    def stop(self):
        self.running = False
