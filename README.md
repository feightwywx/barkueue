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

**ArrayDataSource** — in-memory datasource backed by a `MutableSequence[Task]`.

```python
arr: list[bark.Task] = [bark.Task("order.paid", '{"id":1}')]
ds = bark.datasource.ArrayDataSource(arr)
```

**SqlAlchemyDataSource** — persists to the `barkueue_task` table. barkueue does not depend on SQLAlchemy; install it separately.

```python
from sqlalchemy import create_engine
engine = create_engine("mssql+pyodbc://...")
ds = bark.datasource.SqlAlchemyDataSource(engine)
```

Table schema: `id` (nvarchar(36) PK), `topic`, `message`, `due`, `status`.

### Cron Scheduling

```python
import barkueue as bark

app = bark.app([])
scheduler = bark.Scheduler(app)

@app.handler("report.gen")
def gen_report(app: bark.Application, task: bark.Task) -> None:
    print(f"Generating report: {task.message}")

# Every 5 seconds (6-field cron with seconds)
scheduler.add("* * * * * */5", bark.Task("report.gen", "weekly_report"))

# Every day at 9:00 AM
scheduler.add("0 9 * * *", bark.Task("cleanup", "daily_cleanup"))

app.run()
```

**`bark.Scheduler(app)`** — creates a scheduler with an internal `ArrayDataSource`, auto-appends it to `app.sources`.

**`scheduler.add(cron, task)`** — register a recurring task. The template task's `topic` and `message` are reused for each occurrence; `due` and `id` are overwritten.

Supports both 5-field (`"minute hour dom month dow"`) and 6-field (`"minute hour dom month dow second"`) cron. Depends on `croniter`. Schedules are not persisted across restarts.

### Extending DataSource

`DataSource` is a [Protocol](https://docs.python.org/3/library/typing.html#typing.Protocol) — any object with a `tasks` attribute and the three methods below qualifies.

| Method | Description |
|--------|-------------|
| `fetch()` | Populate `self.tasks` with tasks where `status IS NULL` **and `due <= now`**; must set `task.adapter = self` |
| `update_status(task, status)` | Set `task.status` directly **and** buffer the update. The direct write prevents the task from being re-fetched before `push()` flushes the buffer. |
| `push()` | Flush buffered status updates to storage in a batch |

#### Status Update Flow

Worker calls `task.update_status(status)` → delegates to `adapter.update_status()`, which:

1. **Sets `task.status` directly** — immediately visible when `fetch()` scans for `status is None`.
2. **Buffers the update** for batch persistence in `push()`.

DataSyncWorker cycle order:

```
ds.push()   → flush buffered updates from previous cycle
ds.fetch()  → reload tasks (status IS NULL AND due <= now)
```

#### Thread Safety

Use atomic-swap in `push()`: swap the buffer dict under a lock, then perform I/O outside the lock.

#### Custom DataSource

```python
from barkueue.datasource.type import DataSource
from barkueue.task import Task

class MyDataSource(DataSource):
    tasks: list[Task]

    def __init__(self, ...) -> None:
        self.tasks = []
        self._updated: dict[str, int] = {}

    def fetch(self) -> None:
        """Pull tasks with status None and due <= now, set adapter=self."""
        ...

    def update_status(self, task: Task, status: int) -> None:
        """Set task.status directly AND buffer the update."""
        task.status = status
        self._updated[task.id] = status

    def push(self) -> None:
        """Flush buffered updates to storage."""
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
- [x] cron scheduling
- [ ] retry task
- [x] event system

## License

MIT
