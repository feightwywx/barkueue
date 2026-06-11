import time

import pytest
from sqlalchemy import create_engine

from barkueue.datasource._sqlalchemyds.model import Base


def wait_until(condition, timeout=5, interval=0.05):
    """Poll until *condition* returns truthy, or raise AssertionError on timeout."""
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(interval)
    assert condition(), f"Condition not met within {timeout}s"


@pytest.fixture
def sql_engine():
    """SQLite in-memory engine with barkueue_task table created."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine
