"""Cron-based task scheduling."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from croniter import croniter  # type: ignore[import-untyped]

from barkueue.datasource import ArrayDataSource
from barkueue.event import TASK_AFTER_RUN, Event
from barkueue.task import Task

if TYPE_CHECKING:
    from barkueue.application import Application


def _next_cron_time(cron: str, base: datetime | None = None) -> datetime:
    """Return the next datetime matching *cron* on or after *base*.

    Args:
        cron: A standard 5-field cron expression (``"minute hour dom month dow"``).
        base: The reference datetime. Defaults to ``datetime.now()``.

    Returns:
        The next datetime that matches the cron schedule.
    """
    if base is None:
        base = datetime.now()
    return croniter(cron, base).get_next(datetime)  # type: ignore[return-value]


class Scheduler:
    """Manages recurring cron-based tasks.

    Creates an internal :class:`ArrayDataSource` and registers it with
    *app* on construction so scheduled tasks flow through the normal
    DataSyncWorker fetch → queue → worker pipeline.

    Example::

        app = bark.app([])
        scheduler = bark.Scheduler(app)

        @app.handler("report.gen")
        def gen_report(app, task):
            print(f"生成报告: {task.message}")

        scheduler.add("*/5 * * * *", bark.Task("report.gen", "weekly_report"))
        app.run()
    """

    def __init__(self, app: Application) -> None:
        self._app = app
        self.datasource = ArrayDataSource([])
        app.sources.append(self.datasource)

    def add(self, cron: str, task: Task) -> None:
        """Schedule a recurring task.

        The first occurrence is enqueued immediately with *due* set to
        the next cron time.  After each occurrence completes, a new task
        with the same *topic* and *message* is created for the next
        cron time.

        Args:
            cron: A standard 5-field cron expression
                (``"minute hour dom month dow"``).
            task: Template task whose ``topic`` and ``message`` are reused
                for every occurrence.
        """
        current: list[Task] = [task]

        def _enqueue_next() -> None:
            new_task: Task = Task(task.topic, task.message)
            new_task.due = _next_cron_time(cron)
            current[0] = new_task
            self.datasource._internal.append(new_task)

        @self._app.event(TASK_AFTER_RUN)
        def _reschedule(event: Event) -> None:
            if event.task is current[0]:
                _enqueue_next()

        _enqueue_next()
