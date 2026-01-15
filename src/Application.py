from collections.abc import Callable, MutableSequence
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.orm import Base
from src.Queue import Queue
from src.Worker import Worker


class Application:
    engine: Engine
    executors: dict[str, Callable] = {}
    queues: MutableSequence[Queue] = []
    session_maker: sessionmaker[Session]
    workers: MutableSequence[Worker] = []

    def __init__(
        self,
        engine: Engine,
    ) -> None:
        self.engine = engine
        self.session_maker = sessionmaker(
            bind=engine, autocommit=False, autoflush=False
        )

    def register_exec(self, id: str):
        def dec(func: Callable[[Any], Any]):
            self.executors[id] = func

            def inner(*args, **kwargs):
                return func(*args, **kwargs)

            return inner

        return dec

    def run(self):
        # create task storage table
        Base.metadata.create_all(self.engine)

        # initalize workers
        for queue in self.queues:
            self.workers.append(Worker(self, queue))

        try:
            for worker in self.workers:
                worker.start()

            while True:
                pass
        except KeyboardInterrupt:
            for worker in self.workers:
                worker.stop()
