from __future__ import annotations

from datetime import datetime

from croniter import croniter  # type: ignore[import-untyped]


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
