# barkueue

[English](README.md) | 简体中文

barkueue（读作 *bark-queue*，或简称为 *bark*），是一个设计用于嵌入已有业务系统的任务队列，适用于以下场景：

- 使用关系型数据库存储业务数据
- 没有事件处理器，或事件处理器对于简单场景而言过于复杂

它**不适用**于：

- 作为高性能和/或低延迟的任务队列处理每笔事务
- 替代数据库管理系统原生的外部函数或服务代理

## 使用

### 基本用法

```python
import time

import barkueue as bark

# 支持list作为内存数据源，或者用SQLAlchemy连接数据库。
arr: list[bark.Task] = [
    bark.Task("dog.bark", "Bluey"),
    bark.Task("dog.woof", "Bingo"),
    bark.Task("dog", "I'm *unicorse*, I like to eat children"),
]
ds = bark.datasource.ArrayDataSource(arr)

# 4个worker，持久化同步间隔为5s
app = bark.app([ds], max_workers=4, fetch_interval=5)


@app.handler("dog.#")
def dog_handler(app: bark.Application, task: bark.Task) -> None:
    if task.message.find("*unicorse*") != -1:
        # 出现异常时应该直接抛出，barkueue会处理任务状态
        raise Exception(f"{task.message}")
    # 模拟业务处理
    time.sleep(1)
    print(f"I'm {task.message}, a little puppy!")


@app.handler("dog.bark")
def bark_handler(app: bark.Application, task: bark.Task) -> None:
    # 模拟业务处理
    time.sleep(3)
    print(f"{task.message} says: bark bark!")


@app.handler("dog.woof")
def woof_handler(app: bark.Application, task: bark.Task) -> None:
    # 模拟业务处理
    time.sleep(2)
    print(f"{task.message} says: woof woof!")


app.run()
```

### 预置数据源

**ArrayDataSource** — 内存数据源，底层为 `MutableSequence[Task]`。

```python
arr: list[bark.Task] = [bark.Task("order.paid", '{"id":1}')]
ds = bark.datasource.ArrayDataSource(arr)
```

**SqlAlchemyDataSource** — 持久化到 `barkueue_task` 表。barkueue 不依赖 SQLAlchemy，需按需安装。

```python
from sqlalchemy import create_engine
engine = create_engine("mssql+pyodbc://...")
ds = bark.datasource.SqlAlchemyDataSource(engine)
```

表结构：`id` (nvarchar(36) PK), `topic`, `message`, `due`, `status`。

### 定时任务

```python
import barkueue as bark

app = bark.app([])
scheduler = bark.Scheduler(app)

@app.handler("report.gen")
def gen_report(app: bark.Application, task: bark.Task) -> None:
    print(f"生成报告: {task.message}")

# 每 5 秒执行（6 字段 cron 支持秒）
scheduler.add("* * * * * */5", bark.Task("report.gen", "weekly_report"))

# 每天早上 9:00 执行
scheduler.add("0 9 * * *", bark.Task("cleanup", "daily_cleanup"))

app.run()
```

**`bark.Scheduler(app)`** — 创建调度器，内部持有 `ArrayDataSource` 并自动追加到 `app.sources`。

**`scheduler.add(cron, task)`** — 注册定时任务。模板 task 的 `topic` 和 `message` 每次复用；`due` 和 `id` 会被覆盖。

支持 5 字段（`"分 时 日 月 周"`）和 6 字段（`"分 时 日 月 周 秒"`）cron。依赖 `croniter`。调度不持久化，重启后丢失。

### 数据源拓展

`DataSource` 是 [Protocol](https://docs.python.org/3/library/typing.html#typing.Protocol) — 具有 `tasks` 属性和以下三个方法的对象即满足协议。

| 方法 | 说明 |
|------|------|
| `fetch()` | 拉取 `status IS NULL` **且 `due <= now`** 的任务填充 `self.tasks`；须设 `task.adapter = self` |
| `update_status(task, status)` | **同时**设置 `task.status` 并缓存更新。直接写入防止任务在 `push()` 之前被重复拉取。 |
| `push()` | 将缓存的更新批量刷入存储 |

#### 状态更新流程

Worker 调用 `task.update_status(status)` → 委托给 `adapter.update_status()`，该方法：

1. **直接设置 `task.status`** — 使 `fetch()` 扫描 `status is None` 时立即可见。
2. **缓存更新**，供 `push()` 批量持久化。

DataSyncWorker 循环顺序：

```
ds.push()   → 将上一轮缓存的更新刷入存储
ds.fetch()  → 拉取任务（status IS NULL AND due <= now）
```

#### 线程安全

`push()` 采用 atomic-swap 模式：在锁内换出缓存 dict，释放锁后再做 I/O。

#### 自定义 DataSource

```python
from barkueue.datasource.type import DataSource
from barkueue.task import Task

class MyDataSource(DataSource):
    tasks: list[Task]

    def __init__(self, ...) -> None:
        self.tasks = []
        self._updated: dict[str, int] = {}

    def fetch(self) -> None:
        """拉取 status 为 None 且 due <= now 的任务，设 adapter=self。"""
        ...

    def update_status(self, task: Task, status: int) -> None:
        """同时设置 task.status 并缓存更新。"""
        task.status = status
        self._updated[task.id] = status

    def push(self) -> None:
        """将缓存的更新批量刷入存储。"""
        ...
```

## 事件系统

barkueue 提供六个生命周期事件，允许在任务处理的各个阶段插入自定义逻辑。事件处理器通过 `@app.event()` 装饰器注册。

### 事件列表

| 事件常量 | 触发时机 | Event.task | Event.handler |
|---|---|---|---|
| `APP_BEFORE_RUN` | `run()` 开始，worker 创建之前 | None | None |
| `APP_AFTER_RUN` | 所有 worker 退出后（正常退出和 Ctrl+C 都会触发） | None | None |
| `TASK_BEFORE_RUN` | 任务出队后，查找 handler 之前 | ✓ | None |
| `TASK_AFTER_RUN` | 任务状态更新后，with 块退出前（无匹配 handler 时也会触发） | ✓ | None |
| `HANDLER_BEFORE_RUN` | 每个 handler 调用之前 | ✓ | ✓ |
| `HANDLER_AFTER_RUN` | 每个 handler 返回之后（含异常抛出） | ✓ | ✓ |

### Event 对象

事件处理函数接收一个 `Event` 实例，包含以下字段：

- `app: Application` — 触发事件的 Application 实例
- `task: Task | None` — 当前任务（app 级事件中为 None）
- `handler: Callable | None` — 当前 handler 函数引用（task 级和 app 级事件中为 None）

### 注册事件处理器

```python
import barkueue as bark

@app.event(bark.APP_BEFORE_RUN)
def on_setup(event: bark.Event) -> None:
    # 在 worker 启动前执行初始化逻辑
    ...

@app.event(bark.TASK_AFTER_RUN)
def on_task_done(event: bark.Event) -> None:
    # 在任务完成后执行收尾逻辑
    ...
```

同一事件可注册多个处理器，按注册顺序依次执行。任一处理器抛出异常仅记录日志，不影响后续处理器和主流程。

### 典型场景

**应用启动时自动建表 / 注册触发器：**

```python
@app.event(bark.APP_BEFORE_RUN)
def setup_db(event: bark.Event) -> None:
    event.app.sources[0].engine.execute("CREATE TRIGGER ...")
```

**任务完成后实现重试 / 定时调度：**

```python
@app.event(bark.TASK_AFTER_RUN)
def retry_on_failure(event: bark.Event) -> None:
    if event.task.status == 1:
        # 重新入队
        event.app.queue.put(bark.Task(
            event.task.topic,
            event.task.message,
            due=datetime.now() + timedelta(seconds=30),
        ))
```

### 注意事项

- 事件处理器在触发线程内同步执行——耗时操作会阻塞 worker
- 事件处理器的返回值被忽略
- `handler_before_run` / `handler_after_run` 仅在 topic 有匹配 handler 时触发；无匹配时 `for` 循环体不执行
- `task_after_run` 无论是否有匹配 handler 都会触发

## To-dos

- [x] fetch-consume 事件循环
- [x] fetch 间隔控制
- [x] 数据源diff，将状态更新合并到数据同步工作线程
- [x] 内存数据源
- [x] 定时任务
- [ ] 任务重试
- [x] 事件系统

## License

MIT
