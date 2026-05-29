from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from src.datasource.type import DataSource

DS = TypeVar("DS", bound="DataSource")


@dataclass
class Task(Generic[DS]):
    id: int
    topic: str
    message: str
    due: datetime
    status: int
    adapter: DS | None = None

    def update_status(self, status: int):
        if self.adapter is None:
            raise RuntimeError(f"task {id} is not bound to an adapter")
        return self.adapter.update_status(self, status)

    def __lt__(self, other: Task) -> bool:
        return self.due < other.due

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Task):
            return NotImplemented
        return self.due == other.due

    def __rt__(self, other: Task) -> bool:
        return self.due > other.due
