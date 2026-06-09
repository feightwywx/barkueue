from __future__ import annotations

from collections.abc import MutableSequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.task import Task


class DataSource(Protocol):
    tasks: MutableSequence[Task]
    """
    Buffer populated by fetch(), drained by the caller.

    The caller (DataSyncWorker) drains this list via pop() after each
    fetch() call. Implementations should append new tasks rather than
    replacing the list, so the caller can safely iterate-and-pop.
    """

    def fetch(self) -> None:
        """
        Populate self.tasks with pending (unprocessed) tasks.

        Each task must have its adapter set to self so that
        update_status() calls on the task route back to this datasource.
        Only tasks whose status indicates "unprocessed" (e.g. status is
        None) should be included.

        Callers are expected to drain self.tasks before the next fetch().
        """
        ...

    def update_status(self, task: Task, status: int) -> None:
        """
        Buffer a status update for the given task.

        This method should NOT immediately persist the update. Instead,
        store it internally so that push() can flush all buffered updates
        in a single batch.
        """
        ...

    def push(self) -> None:
        """
        Flush all buffered status updates.

        After a successful push, tasks whose status was updated should
        no longer appear in subsequent fetch() calls (because fetch()
        should only return unprocessed tasks).
        """
        ...
