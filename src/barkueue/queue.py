from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from queue import PriorityQueue
from typing import TYPE_CHECKING

from barkueue.task import Task

if TYPE_CHECKING:
    pass


class DedupPriorityQueue(PriorityQueue[Task]):
    """A PriorityQueue that prevents duplicate task IDs from being enqueued.

    Tasks are ordered by their ``due`` field (via ``Task.__lt__``).
    Once a task is dequeued and processed, call :meth:`dispose` to allow
    the same ID to be enqueued again.
    """

    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize)
        self._queued_ids: set[int] = set()

    def put(self, item: Task, block: bool = True, timeout: float | None = None) -> None:
        """Put a task into the queue, silently skipping duplicate IDs.

        If a task with the same ``id`` is already in the queue (tracked by
        ``_queued_ids``), the item is dropped.
        """
        if item.id not in self._queued_ids:
            self._queued_ids.add(item.id)
            super().put(item, block, timeout)

    def dispose(self, task_id: int) -> None:
        """Release a task ID so it can be re-enqueued.

        Call this after a task has been fully processed (success or failure).
        """
        self._queued_ids.discard(task_id)

    @contextmanager
    def get_context(
        self, timeout: float | None = None
    ) -> Generator[Task, None, None]:
        """Context manager that auto-disposes the task on exit.

        Usage::

            with queue.get_context(timeout=5) as task:
                process(task)
            # task.id is automatically disposed here
        """
        task = self.get(timeout=timeout)
        try:
            yield task
        finally:
            self.dispose(task.id)
