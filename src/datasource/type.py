from collections.abc import Sequence
from typing import Protocol

from src.Task import Task


class DataSource(Protocol):
    tasks: Sequence[Task]
    """
    store tasks.
    """

    def fetch(self) -> None:
        """
        fetch task.
        """
        ...

    def update_status(self, task: Task, status: int) -> None:
        """
        sync task to datasource.
        """
        ...
