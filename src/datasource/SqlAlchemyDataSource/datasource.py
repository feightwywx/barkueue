from collections.abc import MutableSequence
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from src.datasource.SqlAlchemyDataSource.model import ORMTaskTable
from src.datasource.type import DataSource, Task

if TYPE_CHECKING:
    from sqlalchemy import Engine


class SqlAlchemyDataSource(DataSource):
    tasks: MutableSequence[Task]

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._session = sessionmaker(bind=engine)
        self.tasks = []

    def fetch(self) -> None:
        with self._session() as s:
            query = select(ORMTaskTable).where(ORMTaskTable.status.isnot(None))
            task_results = s.execute(query).scalars().all()

            tasks: list[Task] = [
                Task(
                    id=x.id,
                    topic=x.topic,
                    message=x.message,
                    due=x.due,
                    status=x.status,
                )
                for x in task_results
            ]
            self.tasks.extend(tasks)

    def update_status(self, task, status) -> None:
        with self._session() as s:
            update_query = (
                update(ORMTaskTable)
                .where(ORMTaskTable.id == task.id)
                .values(status=status)
            )

            s.execute(update_query)
            s.commit()
