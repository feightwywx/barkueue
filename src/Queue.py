from __future__ import annotations
from collections import deque
from typing import TYPE_CHECKING
from src.orm import BarkueueTask
from sqlalchemy import select, and_


if TYPE_CHECKING:
    from src.Application import Application


class Queue(deque[BarkueueTask]):
    _app: Application
    id: str

    def __init__(self, id: str):
        super().__init__()
        self.id = id

    def bind(self, app: Application):
        self._app = app
        app.queues.append(self)

    def fetch_queue(self):
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
