from __future__ import annotations

from collections.abc import MutableSequence
from threading import Lock
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from barkueue.datasource._sqlalchemyds.model import ORMTaskTable
from barkueue.datasource.type import DataSource
from barkueue.task import Task

if TYPE_CHECKING:
    from sqlalchemy import Engine


class SqlAlchemyDataSource(DataSource):
    tasks: MutableSequence[Task]

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._session = sessionmaker(bind=engine)
        self.tasks = []
        self._updated: dict[int, int] = {}
        self._lock = Lock()

    def fetch(self) -> None:
        with self._session() as s:
            query = select(ORMTaskTable).where(ORMTaskTable.status.is_(None))
            task_results = s.execute(query).scalars().all()

            tasks: list[Task] = [
                Task(
                    id=x.id,
                    topic=x.topic,
                    message=x.message,
                    due=x.due,
                    status=x.status,
                    adapter=self,
                )
                for x in task_results
            ]
            self.tasks.extend(tasks)

    def update_status(self, task, status) -> None:
        with self._lock:
            self._updated[task.id] = status

    def push(self) -> None:
        with self._lock:
            batch = self._updated
            self._updated = {}
        if not batch:
            return
        with self._session() as s:
            for task_id, status in batch.items():
                s.execute(
                    update(ORMTaskTable)
                    .where(ORMTaskTable.id == task_id)
                    .values(status=status)
                )
            s.commit()
