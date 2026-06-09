# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

barkueue 是一个可嵌入现有业务系统的轻量级任务队列。它从关系数据库表中轮询待处理任务，分发到已注册的 handler 并由工作线程执行。设计目标是简单易集成，而非高性能/低延迟——不适合替代专用消息队列。

## 常用命令

```bash
uv run main.py          # 运行 stub 入口
uv run test.py          # 运行集成测试（需要 MSSQL 实例）
uv run ruff check .     # lint
uv run mypy src/        # 类型检查
```

目前没有正式测试套件——`test.py` 是连接真实 SQL Server 运行 app 的集成脚本。

## 架构

```
bark.app([datasources])           # 单例工厂 → Application
  ├── @app.handler("topic.*")     # 装饰器，支持 AMQP 风格 topic 模式匹配
  ├── Worker (×N)                 # 执行线程，从 DedupPriorityQueue 取任务并分发
  ├── DataSyncWorker (×1)         # 数据同步线程，push() → fetch() → 入队
  └── DataSource[]                # 协议：fetch() + update_status() + push()
       ├── SqlAlchemyDataSource   # SQLAlchemy 实现，依赖表 barkueue_task
       └── ArrayDataSource        # 纯内存实现，用于测试
```

**`src/barkueue/__init__.py`** 是公开 API 入口。外部代码通过 `import barkueue as bark` 导入，调用 `bark.app()` 获取单例 `Application`。`app()` 支持参数：`sources`、`max_workers`、`queue_timeout`、`fetch_interval`。

**`Application`** 持有 handler 注册表（`executors: dict[str, Callable]`）、工作线程池和 `DedupPriorityQueue[Task]`。提供 `queue_timeout` 和 `fetch_interval` 属性，Worker 从 app 实例直接读取。`app.run()` 启动 worker 并 block。

**`Task`** 是按 `due` 排序的 dataclass（`due` 越早越优先出队）。持有对所属 `DataSource` 的 `adapter` 引用，`update_status()` 委托给 adapter。

**`DataSource`** 是 Protocol，定义三个方法：
- `fetch()` — 拉取未处理任务填充 `self.tasks`，须设 `adapter=self`
- `update_status(task, status)` — 缓冲状态更新（不立即持久化）
- `push()` — 批量刷入所有缓冲的状态更新

状态更新采用缓冲-批量模式：Worker 线程调 `update_status()` 仅写内存 dict，DataSyncWorker 在每轮 `fetch()` 前调 `push()` 统一刷入。这避免了每次任务完成都产生独立 DB 事务。

**`SqlAlchemyDataSource`** 映射 `barkueue_task` 表（`id, topic, message, due, status`），使用 `select`/`update`。`push()` 在单事务内逐条 UPDATE 后 commit。

**`ArrayDataSource`** 纯内存实现，接收 `MutableSequence[Task]` 作为内部存储，`push()` 通过 id 匹配回写 `_internal`。

**Topic Exchange** 通过 `src/util/exchange.py` 的 `match_topic(pattern, topic)` 实现 AMQP 风格路由键匹配：`.` 分隔段，`*` 匹配单段，`#` 匹配零或多段。`@app.handler("order.*")` 注册的模式可匹配多个 topic。Worker 的 `_get_topic_handlers(topic)` 返回所有匹配的 handler，按注册顺序**全部执行**，任一失败则 task status=1。

**`Worker`** 循环从 `DedupPriorityQueue` 取任务，通过 `_get_topic_handlers()` 查找匹配的 handler，依次执行。异常通过 `_logger.exception()` 打印完整 traceback。`queue_timeout` 直接从 `self.app` 读取。

**日志** 通过 `src/util/logger.py` 输出到 stderr，DEBUG 级别，logger 名为 `"barkueue"`。

## 重要模式

- 全项目使用 `from __future__ import annotations` 以支持 forward-reference 字符串注解。
- 用 `TYPE_CHECKING` 防护仅用于类型检查的 import，避免运行时循环引用。
- `DataSource` 协议使用结构化子类型——任何具有 `tasks`、`fetch()`、`update_status()` 和 `push()` 的对象都满足协议。
- 状态更新缓冲-批量模式：`update_status()` 写内存 dict，`push()` 统一刷入。两个 DataSource 实现行为一致。
- `push()` 使用 atomic-swap（加锁取出旧 dict，换上新空 dict），释放锁后再做 I/O，避免阻塞 Worker 线程。
- `Task.__lt__`（按 `due` 比较）是 `PriorityQueue` 正常工作的前提——没有 `due` 的任务会出错。
- Topic exchange 匹配逻辑在 `src/util/exchange.py`，与 Worker 解耦，可独立测试。
