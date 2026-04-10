from collections.abc import Iterable

import src.datasource as datasource
from src.Application import Application
from src.datasource.type import DataSource
from src.Task import Task

_current_app = None


def app(sources: Iterable[DataSource] = [], max_workers: int = 1) -> Application:
    """
    Create or get a barkueue singleton.

    This function implements a singleton pattern for creating and accessing
    the main barkueue application instance. On first call, it creates a new
    Application instance with the provided sources and worker count. Subsequent
    calls will return the same instance.

    Args:
        sources: Iterable of DataSource instances to initialize the application with
        max_workers: Maximum number of worker threads to use

    Returns:
        Application: The singleton Application instance
    """
    global _current_app
    if _current_app is None:
        _current_app = Application(sources=sources, worker_count=max_workers)
        return _current_app
    else:
        return _current_app


__all__ = ["app", "Application", "DataSource", "Task", "datasource"]
