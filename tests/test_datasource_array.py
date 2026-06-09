import pytest

from barkueue.datasource import ArrayDataSource
from barkueue.task import Task


class TestFetch:
    def test_fetches_tasks_with_status_none(self):
        tasks = [Task("t", "hello"), Task("t", "world")]
        ds = ArrayDataSource(tasks)
        ds.fetch()
        assert len(ds.tasks) == 2

    def test_skips_tasks_with_status_not_none(self):
        tasks = [Task("t", "hello", status=0), Task("t", "world", status=None)]
        ds = ArrayDataSource(tasks)
        ds.fetch()
        assert len(ds.tasks) == 1
        assert ds.tasks[0].message == "world"

    def test_sets_adapter(self):
        tasks = [Task("t", "hello")]
        ds = ArrayDataSource(tasks)
        ds.fetch()
        assert ds.tasks[0].adapter is ds


class TestPush:
    def test_writes_status_to_internal(self):
        internal = [Task("t", "hello")]
        ds = ArrayDataSource(internal)
        ds.fetch()
        ds.update_status(ds.tasks[0], 0)
        ds.push()
        assert internal[0].status == 0

    def test_noop_when_no_updates(self):
        internal = [Task("t", "hello")]
        ds = ArrayDataSource(internal)
        ds.push()  # no error

    def test_last_update_wins_for_same_task(self):
        internal = [Task("t", "hello")]
        ds = ArrayDataSource(internal)
        ds.fetch()
        ds.update_status(ds.tasks[0], 0)
        ds.update_status(ds.tasks[0], 1)
        ds.push()
        assert internal[0].status == 1

    def test_unmatched_id_does_not_crash(self):
        internal = [Task("t", "hello")]
        ds = ArrayDataSource(internal)
        # update a task id that doesn't exist in internal
        ds._updated["nonexistent"] = 0
        ds.push()  # no error


class TestRefetch:
    def test_completed_tasks_not_refetched(self):
        internal = [Task("t", "hello")]
        ds = ArrayDataSource(internal)
        ds.fetch()
        assert len(ds.tasks) == 1
        ds.update_status(ds.tasks[0], 0)
        ds.push()
        # drain tasks
        ds.tasks.clear()
        # re-fetch — should be empty
        ds.fetch()
        assert len(ds.tasks) == 0


class TestInternalReference:
    def test_internal_is_same_list(self):
        internal = [Task("t", "hello")]
        ds = ArrayDataSource(internal)
        assert ds._internal is internal
