from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from barkueue.application import Application
    from barkueue.task import Task

APP_BEFORE_RUN = "app_before_run"
APP_AFTER_RUN = "app_after_run"
TASK_BEFORE_RUN = "task_before_run"
TASK_AFTER_RUN = "task_after_run"
HANDLER_BEFORE_RUN = "handler_before_run"
HANDLER_AFTER_RUN = "handler_after_run"


@dataclass
class Event:
    """Event object passed to event handlers.

    Fields:
        app: The Application instance that fired the event.
        task: The Task being processed (None for app-level events).
        handler: The handler callable being invoked (None for app-level
            and task-level events).
    """

    app: Application
    task: Task | None = None
    handler: Callable | None = None


__all__ = [
    "Event",
    "APP_BEFORE_RUN",
    "APP_AFTER_RUN",
    "TASK_BEFORE_RUN",
    "TASK_AFTER_RUN",
    "HANDLER_BEFORE_RUN",
    "HANDLER_AFTER_RUN",
]
