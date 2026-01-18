from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

from sqlalchemy import and_, select

from src.orm import BarkueueTask

if TYPE_CHECKING:
    from src.Application import Application


class Queue(deque[BarkueueTask]):
    _app: Application | None = None
    _last_fetch: float | None = None
    id: str
    minFetchTimeout: float

    def __init__(self, id: str, minFetchTimeout: float = 0):
        super().__init__()
        self.id = id
        self.minFetchTimeout = minFetchTimeout

    def bind(self, app: Application):
        self._app = app
        app.queues.append(self)

    def fetch_queue(self):
        assert self._app is not None, "Queue is not bound to an Application"

        now = time.time()
        if self._last_fetch is not None and now < (
            due := (self._last_fetch + self.minFetchTimeout)
        ):
            time.sleep(due - now)

        with self._app.session_maker() as s:
            query = (
                select(BarkueueTask)
                .where(
                    and_(BarkueueTask.queue == self.id, BarkueueTask.status.is_(None))
                )
                .order_by(BarkueueTask.created.asc())
            )
            result = s.execute(query).scalars().all()
            self.extend(result)
            self._last_fetch = time.time()
