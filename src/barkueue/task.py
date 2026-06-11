from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Generic, TypeVar
from uuid import uuid4

if TYPE_CHECKING:
    from barkueue.datasource.type import DataSource

DS = TypeVar("DS", bound="DataSource")


@dataclass
class Task(Generic[DS]):
    topic: str
    message: str

    id: str = field(default_factory=lambda: str(uuid4()))
    status: None | int = None
    due: datetime = field(default_factory=datetime.now)
    adapter: DS | None = None

    def update_status(self, status: int):
        if self.adapter is None:
            raise RuntimeError(f"task {self.id} is not bound to an adapter")
        return self.adapter.update_status(self, status)

    def __lt__(self, other: Task) -> bool:
        return self.due < other.due

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Task):
            return NotImplemented
        return self.due == other.due

    def __rt__(self, other: Task) -> bool:
        return self.due > other.due
