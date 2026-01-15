from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

# 创建基类
Base = declarative_base()


class BarkueueTask(Base):  # type: ignore
    __tablename__ = "barkueue_task"

    id = Column(
        String(36),
        primary_key=True,
        nullable=False,
    )
    queue = Column(String(50), nullable=False)
    exec = Column(String(50), nullable=False)
    param = Column(Text, nullable=True)
    created = Column(DateTime(timezone=True), nullable=False)
    last_started = Column(DateTime(timezone=True), nullable=True)
    last_stopped = Column(DateTime(timezone=True), nullable=True)
    status = Column(Integer(), nullable=True)

    def __repr__(self):
        return f"<BarkueueTaskStorageModel(bark_id={self.bark_id})>"
