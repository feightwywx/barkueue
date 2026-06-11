from datetime import datetime

from sqlalchemy import text

from barkueue.datasource._sqlalchemyds.datasource import SqlAlchemyDataSource


def _insert_row(session, **kwargs):
    defaults = {
        "id": "1",
        "topic": "test",
        "message": "hello",
        "due": datetime(2020, 1, 1),
        "status": None,
    }
    defaults.update(kwargs)
    session.execute(
        text(
            "INSERT INTO barkueue_task (id, topic, message, due, status) "
            "VALUES (:id, :topic, :message, :due, :status)"
        ),
        defaults,
    )
    session.commit()


def _count_rows(session):
    return session.execute(text("SELECT COUNT(*) FROM barkueue_task")).scalar()


class TestFetch:
    def test_fetches_null_status(self, sql_engine):
        ds = SqlAlchemyDataSource(sql_engine)
        with ds._session() as s:
            _insert_row(s, id="1", status=None)
            _insert_row(s, id="2", status=0)

        ds.fetch()
        assert len(ds.tasks) == 1
        assert ds.tasks[0].id == "1"

    def test_sets_adapter(self, sql_engine):
        ds = SqlAlchemyDataSource(sql_engine)
        with ds._session() as s:
            _insert_row(s, id="1")

        ds.fetch()
        assert ds.tasks[0].adapter is ds


class TestPush:
    def test_updates_db_status(self, sql_engine):
        ds = SqlAlchemyDataSource(sql_engine)
        with ds._session() as s:
            _insert_row(s, id="1", status=None)

        ds.fetch()
        task = ds.tasks[0]
        ds.update_status(task, 0)
        ds.push()

        with ds._session() as s:
            result = s.execute(
                text("SELECT status FROM barkueue_task WHERE id = '1'")
            ).scalar()
        assert result == 0

    def test_batch_updates(self, sql_engine):
        ds = SqlAlchemyDataSource(sql_engine)
        with ds._session() as s:
            _insert_row(s, id="1")
            _insert_row(s, id="2")
            _insert_row(s, id="3")

        ds.fetch()
        assert len(ds.tasks) == 3
        for task in ds.tasks:
            ds.update_status(task, 0)
        ds.push()

        with ds._session() as s:
            for row_id in ["1", "2", "3"]:
                status = s.execute(
                    text("SELECT status FROM barkueue_task WHERE id = :id"),
                    {"id": row_id},
                ).scalar()
                assert status == 0

    def test_last_update_wins(self, sql_engine):
        ds = SqlAlchemyDataSource(sql_engine)
        with ds._session() as s:
            _insert_row(s, id="1")

        ds.fetch()
        ds.update_status(ds.tasks[0], 1)
        ds.update_status(ds.tasks[0], 0)
        ds.push()

        with ds._session() as s:
            status = s.execute(
                text("SELECT status FROM barkueue_task WHERE id = '1'")
            ).scalar()
        assert status == 0

    def test_empty_push_is_noop(self, sql_engine):
        ds = SqlAlchemyDataSource(sql_engine)
        ds.push()  # no error


class TestRefetch:
    def test_pushed_tasks_not_refetched(self, sql_engine):
        ds = SqlAlchemyDataSource(sql_engine)
        with ds._session() as s:
            _insert_row(s, id="1")

        ds.fetch()
        assert len(ds.tasks) == 1
        ds.update_status(ds.tasks[0], 0)
        ds.push()
        ds.tasks.clear()

        ds.fetch()
        assert len(ds.tasks) == 0
