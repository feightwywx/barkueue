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

barkueue 自带2种数据源：内存数据源和基于SqlAlchemy的ORM持久化数据源。

**ArrayDataSource** — 内存数据源。

```python
arr: list[bark.Task] = [bark.Task("order.paid", '{"id":1}')]
ds = bark.datasource.ArrayDataSource(arr)
```

`arr` 既是输入也是输出——`push()` 会回写 `status` 到 `arr` 中的 `Task` 对象。

**SqlAlchemyDataSource** — 持久化到 `barkueue_task` 表。barkueue 不依赖 SQLAlchemy，需要按需安装。

```python
from sqlalchemy import create_engine
engine = create_engine("mssql+pyodbc://...")
ds = bark.datasource.SqlAlchemyDataSource(engine)
```

表结构：`id` (int PK), `topic`, `message`, `due`, `status`。`fetch()` 拉取 `status IS NULL` 的行，`push()` 批量 UPDATE。

### 数据源拓展

`DataSource` 是 barkueue 与外部存储之间的抽象层，定义了三个方法：

| 方法 | 说明 |
|------|------|
| `fetch()` | 拉取未处理的任务填充 `self.tasks`，须将 `task.adapter` 设为 `self` |
| `update_status(task, status)` | 缓存状态更新，**不立即持久化** |
| `push()` | 将缓存的状态更新批量刷入存储 |

`DataSource` 是 [Protocol](https://docs.python.org/3/library/typing.html#typing.Protocol)，任何具有上述三个方法与 `tasks` 属性的对象均满足协议，无需显式继承。

#### 状态更新流程

Worker 线程完成任务后调用 `task.update_status(status)`，该方法委托给 `adapter.update_status()`。出于性能考虑，`update_status()` **仅写入内存缓存**（如 dict），真正的持久化发生在 `push()`。

`DataSyncWorker` 每轮循环按以下顺序操作：

```
ds.push()   → 将上一轮缓存的状态更新批量刷入存储
ds.fetch()  → 重新拉取未处理的任务
```

先 push 后 fetch 可确保已完成的 task 不会被重复拉取。因进程崩溃导致未 push 的更新丢失是已知的——对幂等性有要求的 handler 需自行处理。

#### 线程安全

`push()` 实现应采用 atomic-swap 模式：在锁内将缓存 dict 换出，释放锁后再做 I/O。Worker 线程只需加锁写入新 dict，不会被 push 阻塞。

#### 自定义 DataSource

实现协议中的四个成员即可：

```python
from src.datasource.type import DataSource
from src.task import Task

class MyDataSource(DataSource):
    tasks: list[Task]

    def __init__(self, ...) -> None:
        self.tasks = []
        self._updated: dict[str, int] = {}
        ...

    def fetch(self) -> None:
        """拉取 status 为 None 的 task，设 adapter=self 后加入 tasks。"""
        ...

    def update_status(self, task: Task, status: int) -> None:
        """缓存状态更新，不直接写存储。"""
        self._updated[task.id] = status

    def push(self) -> None:
        """将 self._updated 中的更新批量刷入存储。"""
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

**记录每个 handler 的执行耗时：**

```python
@app.event(bark.HANDLER_BEFORE_RUN)
def start_timer(event: bark.Event) -> None:
    event._start = time.monotonic()

@app.event(bark.HANDLER_AFTER_RUN)
def log_elapsed(event: bark.Event) -> None:
    elapsed = time.monotonic() - event._start
    print(f"handler {event.handler.__name__} took {elapsed:.2f}s")
```

### 注意事项

- 事件处理器在触发线程内同步执行——耗时操作会阻塞 worker
- 事件处理器的返回值被忽略
- `handler_before_run` / `handler_after_run` 仅在 topic 有匹配 handler 时触发；无匹配时 `for` 循环体不执行
- `task_after_run` 无论是否有匹配 handler 都会触发

## 定时任务

`app.schedule(cron, task)` 基于 cron 表达式创建周期性任务。首次触发立即入队（`due` 设为下一次 cron 匹配时间），之后每次任务完成后自动排定下一次入队。

```python
import barkueue as bark

app = bark.app([ds])

@app.handler("report.gen")
def gen_report(app: bark.Application, task: bark.Task) -> None:
    print(f"生成报告: {task.message}")

# 每 5 分钟执行一次
app.schedule("*/5 * * * *", bark.Task("report.gen", "weekly_report"))

# 每天早上 9:00 执行
app.schedule("0 9 * * *", bark.Task("cleanup", "daily_cleanup"))

app.run()
```

### 工作原理

- 首次调用 `schedule()` 时，先注册 `TASK_AFTER_RUN` 事件处理器，再计算下一次 cron 时间并入队首个任务（先注册后入队，避免竞态）
- 每次任务完成后，处理器创建新的 `Task`（相同 `topic` 和 `message`，`due` 为下一次 cron 匹配时间）并入队，形成无限链式调度
- 同一 schedule 的多次触发通过 Python 对象标识（`is`）精确匹配，互不干扰
- 新任务自动继承模板的 `adapter`，确保状态更新正常工作

### 注意事项

- 依赖 `croniter` 库解析 cron 表达式，支持标准 5 字段 cron
- 不支持取消调度——调用 `schedule()` 后将持续触发直到 app 停止
- 每次触发生成全新 Task（唯一 UUID），因此不会被 `DedupPriorityQueue` 去重
- 若 app 重启，所有调度丢失（不持久化）

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
