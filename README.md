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

## Event System

barkueue provides six lifecycle events that allow custom logic to be inserted at various stages of task processing. Event handlers are registered via the `@app.event()` decorator.

### Event List

| Event Constant | When | Event.task | Event.handler |
|---|---|---|---|
| `APP_BEFORE_RUN` | Start of `run()`, before worker creation | None | None |
| `APP_AFTER_RUN` | After all workers exit (both normal exit and Ctrl+C) | None | None |
| `TASK_BEFORE_RUN` | After dequeue, before handler lookup | ✓ | None |
| `TASK_AFTER_RUN` | After status update, before `with` block exits (fires even with no matching handler) | ✓ | None |
| `HANDLER_BEFORE_RUN` | Before each handler invocation | ✓ | ✓ |
| `HANDLER_AFTER_RUN` | After each handler returns (including on exception) | ✓ | ✓ |

### Event Object

Event handlers receive an `Event` instance with the following fields:

- `app: Application` — the Application instance that fired the event
- `task: Task | None` — the current task (None for app-level events)
- `handler: Callable | None` — reference to the handler function being invoked (None for app-level and task-level events)

### Registering Event Handlers

```python
import barkueue as bark

@app.event(bark.APP_BEFORE_RUN)
def on_setup(event: bark.Event) -> None:
    # Run initialization before workers start
    ...

@app.event(bark.TASK_AFTER_RUN)
def on_task_done(event: bark.Event) -> None:
    # Run cleanup after a task completes
    ...
```

Multiple handlers can be registered for the same event; they execute in registration order. If a handler raises an exception, it is logged but does not prevent subsequent handlers or the main flow from continuing.

### Common Use Cases

**Create DB tables / triggers on startup:**

```python
@app.event(bark.APP_BEFORE_RUN)
def setup_db(event: bark.Event) -> None:
    event.app.sources[0].engine.execute("CREATE TRIGGER ...")
```

**Retry / scheduled re-enqueue after task completion:**

```python
@app.event(bark.TASK_AFTER_RUN)
def retry_on_failure(event: bark.Event) -> None:
    if event.task.status == 1:
        event.app.queue.put(bark.Task(
            event.task.topic,
            event.task.message,
            due=datetime.now() + timedelta(seconds=30),
        ))
```

**Measure per-handler execution time:**

```python
@app.event(bark.HANDLER_BEFORE_RUN)
def start_timer(event: bark.Event) -> None:
    event._start = time.monotonic()

@app.event(bark.HANDLER_AFTER_RUN)
def log_elapsed(event: bark.Event) -> None:
    elapsed = time.monotonic() - event._start
    print(f"handler {event.handler.__name__} took {elapsed:.2f}s")
```

### Notes

- Event handlers execute synchronously in the firing thread — blocking operations will stall the worker
- Return values from event handlers are ignored
- `handler_before_run` / `handler_after_run` only fire when the topic has matching handlers; the `for` loop body does not execute otherwise
- `task_after_run` always fires regardless of whether a handler matched the topic

## To-dos

- [x] fetch-consume event loop
- [x] fetch interval control
- [x] datasource diff, merge status update into data sync worker
- [x] in-memory datasource
- [ ] retry task
- [x] event system

## License

MIT
