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

## To-dos

- [x] fetch-consume 事件循环
- [x] fetch 间隔控制
- [x] 数据源diff，将状态更新合并到数据同步工作线程
- [x] 内存数据源
- [ ] 任务重试
- [ ] 事件系统（如 `@app.init`）

## License

MIT
