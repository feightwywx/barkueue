import pytest
from sqlalchemy import create_engine

from barkueue.datasource._sqlalchemyds.model import Base


@pytest.fixture
def sql_engine():
    """SQLite in-memory engine with barkueue_task table created."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine
