# barkueue

English | [简体中文](README_zh.md)

barkueue (*bark-queue*, or simply *bark*), is a task queue designed to embed into an existing business system, which is:

- Uses a relational database to store business data
- Has no event processor, or an event processor is overkill for the use case

It's **NOT** intended to:

- Act as a high-performance and/or low-latency task queue processing every transaction
- Replace the native external function or service broker of a DBMS

## Usage

### Basic Usage

```python
import time

import barkueue as bark

# Use a list as an in-memory datasource, or connect to a database via SQLAlchemy.
arr: list[bark.Task] = [
    bark.Task("dog.bark", "Bluey"),
    bark.Task("dog.woof", "Bingo"),
    bark.Task("dog", "I'm *unicorse*, I like to eat children"),
]
ds = bark.datasource.ArrayDataSource(arr)

# 4 workers, persistence sync interval of 5s
app = bark.app([ds], max_workers=4, fetch_interval=5)


@app.handler("dog.#")
def dog_handler(app: bark.Application, task: bark.Task) -> None:
    if task.message.find("*unicorse*") != -1:
        # Let exceptions propagate — barkueue handles task status
        raise Exception(f"{task.message}")
    # Simulate business logic
    time.sleep(1)
    print(f"I'm {task.message}, a little puppy!")


@app.handler("dog.bark")
def bark_handler(app: bark.Application, task: bark.Task) -> None:
    # Simulate business logic
    time.sleep(3)
    print(f"{task.message} says: bark bark!")


@app.handler("dog.woof")
def woof_handler(app: bark.Application, task: bark.Task) -> None:
    # Simulate business logic
    time.sleep(2)
    print(f"{task.message} says: woof woof!")


app.run()
```

### Built-in DataSources

barkueue ships with 2 datasources: an in-memory datasource and a SQLAlchemy-based ORM persistent datasource.

**ArrayDataSource** — in-memory datasource.

```python
arr: list[bark.Task] = [bark.Task("order.paid", '{"id":1}')]
ds = bark.datasource.ArrayDataSource(arr)
```

`arr` serves as both input and output — `push()` writes `status` back to the `Task` objects in `arr`.

**SqlAlchemyDataSource** — persists to the `barkueue_task` table. barkueue does not depend on SQLAlchemy; install it separately as needed.

```python
from sqlalchemy import create_engine
engine = create_engine("mssql+pyodbc://...")
ds = bark.datasource.SqlAlchemyDataSource(engine)
```

Table schema: `id` (int PK), `topic`, `message`, `due`, `status`. `fetch()` pulls rows where `status IS NULL`, `push()` performs a batch UPDATE.

### Extending DataSource

`DataSource` is the abstraction layer between barkueue and external storage. It defines three methods:

| Method | Description |
|--------|-------------|
| `fetch()` | Populate `self.tasks` with unprocessed tasks; must set `task.adapter = self` |
| `update_status(task, status)` | Buffer a status update — do **not** persist immediately |
| `push()` | Flush buffered status updates to storage in a batch |

`DataSource` is a [Protocol](https://docs.python.org/3/library/typing.html#typing.Protocol). Any object with the above three methods and a `tasks` attribute satisfies the protocol — no explicit inheritance required.

#### Status Update Flow

When a Worker finishes a task, it calls `task.update_status(status)`, which delegates to `adapter.update_status()`. For performance, `update_status()` **only writes to an in-memory buffer** (e.g. a dict); the actual persistence happens in `push()`.

Each cycle, the `DataSyncWorker` operates in this order:

```
ds.push()   → flush buffered status updates from the previous cycle
ds.fetch()  → reload unprocessed tasks
```

Push-before-fetch ensures completed tasks are not re-fetched. Status updates lost due to a process crash before `push()` is a known trade-off — handlers that require idempotency should account for this.

#### Thread Safety

`push()` implementations should use an atomic-swap pattern: swap out the buffer dict under a lock, then perform I/O outside the lock. Worker threads only need the lock to write to the new dict and are never blocked by I/O.

#### Custom DataSource

Implement the four protocol members:

```python
from barkueue.datasource.type import DataSource
from barkueue.task import Task

class MyDataSource(DataSource):
    tasks: list[Task]

    def __init__(self, ...) -> None:
        self.tasks = []
        self._updated: dict[str, int] = {}
        ...

    def fetch(self) -> None:
        """Pull tasks with status None, set adapter=self, append to tasks."""
        ...

    def update_status(self, task: Task, status: int) -> None:
        """Buffer the update — do not write to storage directly."""
        self._updated[task.id] = status

    def push(self) -> None:
        """Flush buffered updates in self._updated to storage."""
        ...
```

## To-dos

- [x] fetch-consume event loop
- [x] fetch interval control
- [x] datasource diff, merge status update into data sync worker
- [x] in-memory datasource
- [ ] retry task
- [ ] event system (e.g. `@app.init`)

## License

MIT
