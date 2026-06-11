# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

barkueue 是一个可嵌入现有业务系统的轻量级任务队列。它从关系数据库表中轮询待处理任务，分发到已注册的 handler 并由工作线程执行。设计目标是简单易集成，而非高性能/低延迟——不适合替代专用消息队列。

## 常用命令

```bash
uv run pytest tests/ -v     # 运行测试套件
uv run ruff check .         # lint
uv run mypy src/            # 类型检查
```

测试使用 pytest，配置在 `pyproject.toml`（`pythonpath = ["src"]`）。不需要 `test.py`。

## 架构

```
bark.app([datasources])           # 单例工厂 → Application
  ├── @app.handler("topic.*")     # 装饰器，支持 AMQP 风格 topic 模式匹配
  ├── @app.event("event_name")    # 装饰器，注册生命周期事件处理器
  ├── Worker (×N)                 # 执行线程，从 DedupPriorityQueue 取任务并分发
  ├── DataSyncWorker (×1)         # 数据同步线程，push() → fetch() → 入队
  ├── DataSource[]                # 协议：fetch() + update_status() + push()
  │    ├── SqlAlchemyDataSource   # SQLAlchemy 实现，依赖表 barkueue_task
  │    └── ArrayDataSource        # 纯内存实现，用于测试
  ├── Scheduler                   # cron 定时调度，内部持有 ArrayDataSource
  │    └── scheduler.add(cron, task)  # 注册定时任务，走 DataSyncWorker 统一管线
  └── Event                       # dataclass: app + task + handler
       ├── APP_BEFORE_RUN / APP_AFTER_RUN       (Application.run)
       ├── TASK_BEFORE_RUN / TASK_AFTER_RUN     (Worker.loop)
       └── HANDLER_BEFORE_RUN / HANDLER_AFTER_RUN (Worker.loop)
```

**`src/barkueue/__init__.py`** 是公开 API 入口。外部代码通过 `import barkueue as bark` 导入，调用 `bark.app()` 获取单例 `Application`。`app()` 支持参数：`sources`（`MutableSequence[DataSource]`）、`max_workers`、`queue_timeout`、`fetch_interval`。同时导出 `Scheduler`、`Event` 和六个事件名常量。

**`src/barkueue/event.py`** 定义 `Event` dataclass（`app`, `task`, `handler` 三个字段）和六个事件名字符串常量。`Application` 和 `Task` 在 `TYPE_CHECKING` 下导入以避免循环引用。

**`Application`** 持有 handler 注册表（`executors: dict[str, Callable]`）、工作线程池和 `DedupPriorityQueue[Task]`。提供 `queue_timeout` 和 `fetch_interval` 属性，Worker 从 app 实例直接读取。`sources` 类型为 `MutableSequence[DataSource]`，构造时转为 list，允许后续 append（如 Scheduler 自动注册 datasource）。`app.run()` 启动 DataSyncWorker 和 Worker 并 block。

**`Task`** 是按 `due` 排序的 dataclass（`due` 越早越优先出队）。持有对所属 `DataSource` 的 `adapter` 引用，`update_status()` 委托给 adapter。

**`DataSource`** 是 Protocol，定义三个方法：
- `fetch()` — 拉取 `status is None` 且 `due <= now` 的任务填充 `self.tasks`，须设 `adapter=self`。`due` 过滤确保未来任务在当前时间点不被拉取。
- `update_status(task, status)` — **同时**设置 `task.status = status`（立即在 Task 对象上可见）并缓冲到内部 dict，避免 `push()` 前被重复 fetch。
- `push()` — 批量刷入所有缓冲的状态更新到持久存储。

`update_status()` 直接设置 `task.status` 解决了 DataSyncWorker 的 push→fetch 顺序带来的竞态：Worker 在两次操作之间更新了状态，但 `fetch()` 读 `_internal` 时 `push()` 还没把缓冲写回，导致已处理任务被重复拉取。

**`SqlAlchemyDataSource`** 映射 `barkueue_task` 表（`id, topic, message, due, status`），使用 `select`/`update`。`push()` 在单事务内逐条 UPDATE 后 commit。

**`ArrayDataSource`** 纯内存实现，接收 `MutableSequence[Task]` 作为内部存储，`push()` 通过 id 匹配回写 `_internal`。

**`Scheduler`** 在 `src/util/schedule.py`，管理 cron 定时任务。构造时传入 `app`，内部创建 `ArrayDataSource` 并自动 `app.sources.append(self.datasource)` 注册。`add(cron, task)` 将任务模板的 topic/message 按 cron 表达式定时推入 data source，走 DataSyncWorker → queue → Worker 统一管线。`_next_cron_time(cron, base)` 也在本模块。用法：

```python
scheduler = bark.Scheduler(app)
scheduler.add("*/5 * * * * *", bark.Task("report.gen", "weekly_report"))
```

**Topic Exchange** 通过 `src/util/exchange.py` 的 `match_topic(pattern, topic)` 实现 AMQP 风格路由键匹配：`.` 分隔段，`*` 匹配单段，`#` 匹配零或多段。`@app.handler("order.*")` 注册的模式可匹配多个 topic。Worker 的 `_get_topic_handlers(topic)` 返回所有匹配的 handler，按注册顺序**全部执行**，任一失败则 task status=1。

**`Worker`** 循环从 `DedupPriorityQueue` 取任务，通过 `_get_topic_handlers()` 查找匹配的 handler，依次执行。异常通过 `_logger.exception()` 打印完整 traceback。`queue_timeout` 直接从 `self.app` 读取。在 `loop()` 中依次触发 `TASK_BEFORE_RUN`、`HANDLER_BEFORE_RUN`、`HANDLER_AFTER_RUN`、`TASK_AFTER_RUN`。

**事件系统** 通过 `@app.event(name)` 装饰器注册处理器，存入 `Application.events: dict[str, list[Callable]]`。`_fire_event(name, task, handler)` 构造 `Event` 并依次调用已注册的函数。六个事件分布在两个触发点：

- `Application.run()` — `APP_BEFORE_RUN`（workers 创建前）、`APP_AFTER_RUN`（所有 workers join 后）
- `Worker.loop()` — `TASK_BEFORE_RUN`（出队后）、`TASK_AFTER_RUN`（状态更新后，含无匹配 handler 时）、`HANDLER_BEFORE_RUN` / `HANDLER_AFTER_RUN`（每个 handler 调用前后）

事件处理器异常仅记录日志，不向上传播。`handler_*` 事件仅在 topic 有匹配 handler 时触发（位于 `for` 循环体内）。

**日志** 通过 `src/util/logger.py` 输出到 stderr，DEBUG 级别，logger 名为 `"barkueue"`。

## 重要模式

- 全项目使用 `from __future__ import annotations` 以支持 forward-reference 字符串注解。
- 用 `TYPE_CHECKING` 防护仅用于类型检查的 import，避免运行时循环引用。
- `DataSource` 协议使用结构化子类型——任何具有 `tasks`、`fetch()`、`update_status()` 和 `push()` 的对象都满足协议。
- 状态更新缓冲-批量模式：`update_status()` 写内存 dict，`push()` 统一刷入。两个 DataSource 实现行为一致。
- `push()` 使用 atomic-swap（加锁取出旧 dict，换上新空 dict），释放锁后再做 I/O，避免阻塞 Worker 线程。
- `Task.__lt__`（按 `due` 比较）是 `PriorityQueue` 正常工作的前提——没有 `due` 的任务会出错。
- `fetch()` 只拉取 `due <= now` 的任务，未来任务留在 data source 中。这是定时执行的核心机制。
- `update_status()` 同时设置 `task.status` 并缓冲，防止 DataSyncWorker 的 push→fetch 间隙中已处理任务被重新拉取。
- `app.sources` 类型为 `MutableSequence[DataSource]`，构造时转 list。`Scheduler.__init__` 通过 `app.sources.append()` 自动注册自己的 data source。
- 调度系统 `Scheduler` 在 `src/util/schedule.py`，与 `Application` 解耦。用户手工创建 `Scheduler(app)` 并调用 `scheduler.add()`。
- Topic exchange 匹配逻辑在 `src/util/exchange.py`，与 Worker 解耦，可独立测试。
- 事件处理器通过 `@app.event(name)` 注册到 `self.events[name]` 列表，按注册顺序执行。任一处理器抛异常仅记日志，不影响后续处理器和主流程。
- `TASK_AFTER_RUN` 在 status update **之后**触发（处理函数可以读到 `task.status` 的最终值）。
- `TASK_AFTER_RUN` 在无匹配 handler 时也会触发；`HANDLER_BEFORE_RUN` / `HANDLER_AFTER_RUN` 仅在 `for handler in handlers` 循环体内触发。
- `Application._fire_event()` 是私有方法，由 `Application.run()` 和 `Worker.loop()` 内部调用。
