from __future__ import annotations

from collections.abc import MutableSequence
from datetime import datetime

from barkueue.datasource.type import DataSource
from barkueue.task import Task


class ArrayDataSource(DataSource):
    tasks: MutableSequence[Task]

    def __init__(self, internal: MutableSequence[Task]) -> None:
        self._internal = internal
        self.tasks: MutableSequence[Task] = []
        self._updated: dict[str, int] = {}

    def fetch(self) -> None:
        now = datetime.now()
        for task in self._internal:
            if task.status is None and task.due <= now:
                task.adapter = self
                self.tasks.append(task)

    def update_status(self, task: Task, status: int) -> None:
        self._updated[task.id] = status

    def push(self) -> None:
        if not self._updated:
            return
        id_to_task = {t.id: t for t in self._internal}
        for task_id, status in self._updated.items():
            if task_id in id_to_task:
                id_to_task[task_id].status = status
        self._updated = {}
