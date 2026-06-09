from datetime import datetime
from queue import Empty

import pytest

from barkueue.queue import DedupPriorityQueue
from barkueue.task import Task


def make_task(topic="test", msg="hello", id=None, due=None):
    kwargs = {"topic": topic, "message": msg}
    if id is not None:
        kwargs["id"] = id
    if due is not None:
        kwargs["due"] = due
    return Task(**kwargs)


class TestDedup:
    def test_same_id_only_queued_once(self):
        q = DedupPriorityQueue()
        t1 = make_task(id="abc")
        t2 = make_task(id="abc")
        q.put(t1)
        q.put(t2)
        assert q.qsize() == 1

    def test_different_ids_both_queued(self):
        q = DedupPriorityQueue()
        q.put(make_task(id="a"))
        q.put(make_task(id="b"))
        assert q.qsize() == 2


class TestGetContext:
    def test_auto_dispose(self):
        q = DedupPriorityQueue()
        t = make_task(id="x")
        q.put(t)
        with q.get_context(timeout=1) as task:
            assert task.id == t.id
        # After context, same id can be re-enqueued
        q.put(make_task(id="x"))
        assert q.qsize() == 1

    def test_raises_empty_on_timeout(self):
        q = DedupPriorityQueue()
        with pytest.raises(Empty):
            q.get(timeout=0.1)


class TestPriority:
    def test_due_order(self):
        q = DedupPriorityQueue()
        early = make_task(id="a", due=datetime(2020, 1, 1))
        late = make_task(id="b", due=datetime(2020, 6, 1))
        q.put(late)
        q.put(early)
        assert q.get(timeout=0.1).id == "a"
        assert q.get(timeout=0.1).id == "b"
