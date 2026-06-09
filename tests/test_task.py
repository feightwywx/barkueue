from datetime import datetime, timedelta

import pytest

from barkueue.task import Task


class TestComparison:
    def test_lt_by_due(self):
        early = Task("t", "msg", due=datetime(2020, 1, 1))
        late = Task("t", "msg", due=datetime(2020, 6, 1))
        assert early < late

    def test_lt_not_equal(self):
        early = Task("t", "msg", due=datetime(2020, 1, 1))
        late = Task("t", "msg", due=datetime(2020, 1, 1))
        assert not (early < late)

    def test_eq_by_due(self):
        t1 = Task("t", "msg", due=datetime(2020, 1, 1))
        t2 = Task("t", "msg", due=datetime(2020, 1, 1))
        assert t1 == t2

    def test_eq_not_different_due(self):
        t1 = Task("t", "msg", due=datetime(2020, 1, 1))
        t2 = Task("t", "msg", due=datetime(2020, 6, 1))
        assert t1 != t2


class TestUpdateStatus:
    def test_delegates_to_adapter(self):
        class FakeAdapter:
            def update_status(self, task, status):
                self.called_with = (task, status)

        adapter = FakeAdapter()
        task = Task("t", "msg", adapter=adapter)
        task.update_status(0)
        assert adapter.called_with == (task, 0)

    def test_raises_when_no_adapter(self):
        task = Task("t", "msg")
        with pytest.raises(RuntimeError, match="not bound to an adapter"):
            task.update_status(0)


class TestDefaults:
    def test_id_is_unique_per_instance(self):
        t1 = Task("t", "msg")
        t2 = Task("t", "msg")
        assert t1.id != t2.id

    def test_id_is_string(self):
        t = Task("t", "msg")
        assert isinstance(t.id, str)
        assert len(t.id) > 0

    def test_due_is_default_now(self):
        t = Task("t", "msg")
        assert isinstance(t.due, datetime)

    def test_due_is_independent_per_instance(self):
        t1 = Task("t", "msg", due=datetime(2020, 1, 1))
        t2 = Task("t", "msg")
        # t2.due should be a recent timestamp, not 2020
        assert t2.due > datetime(2020, 1, 2)

    def test_status_defaults_to_none(self):
        t = Task("t", "msg")
        assert t.status is None
