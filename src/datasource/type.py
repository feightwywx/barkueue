from __future__ import annotations

from collections.abc import MutableSequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.Task import Task


class DataSource(Protocol):
    tasks: MutableSequence[Task]
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

    def push(self) -> None:
        """
        flush buffered status updates to the datasource.
        """
        ...
