from __future__ import annotations
from typing import TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from src.Queue import Queue
    from src.Application import Application


class Worker:
    _app: Application
    running: bool = True
    queue: Queue

    def __init__(self, _app: Application, queue: Queue) -> None:
        self._app = _app
        self.queue = queue

    def loop(self):
        from sqlalchemy import update
        from src.orm import BarkueueTask

        while self.running:
            self.queue.fetch_queue()

            while True:
                try:
                    task = self.queue.pop()
                except IndexError:
                    break

                with self._app.session_maker() as s:
                    exec = self._app.executors[str(task.exec)]
                    param = str(task.param)

                    exec(param)

                    s.execute(
                        update(BarkueueTask)
                        .values(status="1")
                        .where(BarkueueTask.id == task.id)
                    )

                    s.commit()

    def start(self):
        thread = threading.Thread(target=self.loop)
        thread.start()


    def stop(self):
        self.running = False
