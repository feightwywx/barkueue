from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ORMTaskTable(Base):
    __tablename__ = "barkueue_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    due: Mapped[datetime] = mapped_column(DateTime(), nullable=True)
    status: Mapped[int] = mapped_column(Integer(), nullable=True)

    def __repr__(self):
        return f"<ORMTaskTable(id={self.id})>"
