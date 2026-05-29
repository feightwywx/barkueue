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
bark.app([datasources])   # 单例工厂 → Application
  ├── @app.handler("id")  # 装饰器，按 task id 注册处理函数
  ├── Worker (×N)         # threading.Thread 循环，从 PriorityQueue 取任务并分发
  └── DataSource[]        # 协议：fetch() + update_status(task, status)
       └── SqlAlchemyDataSource  # 依赖表 barkueue_task（见 model.py）
```

**`src/__init__.py`** 是公开 API 入口。外部代码通过 `import src as bark` 导入，调用 `bark.app()` 获取单例 `Application`。

**`Application`** 持有 handler 注册表（`executors: dict[str, Callable]`）、工作线程池和 `PriorityQueue[Task]`。`app.run()` 启动 worker 并 block。

**`Task`** 是按 `due` 排序的 dataclass（`due` 越早越优先出队）。它持有对所属 `DataSource` 的可选引用，以便在任务完成后调用 `update_status()` 回写结果。

**`DataSource`** 是 Protocol，定义了两个方法：`fetch()` 从持久层拉取待处理任务，`update_status()` 将任务结果写回。

**`SqlAlchemyDataSource`** 是当前唯一的 DataSource 实现。映射到 `barkueue_task` 表（列：`id, topic, message, due, status`），使用原生 `select`/`update` 而非完整的工作单元模式。

**`Worker`** 循环调用 `Queue.get()`，根据 task id 查找 handler，执行并在完成后更新状态（成功 0，失败 1）。Worker 持有自己的 `Thread` 实例以控制生命周期（start/join/stop）。

**日志** 通过 `src/util/logger.py` 输出到 stderr，DEBUG 级别，logger 名为 `"barkueue"`。

## 重要模式

- 全项目使用 `from __future__ import annotations` 以支持 forward-reference 字符串注解。
- 用 `TYPE_CHECKING` 防护仅用于类型检查的 import，避免运行时循环引用。
- `DataSource` 协议使用结构化子类型——任何具有 `tasks`、`fetch()` 和 `update_status()` 的对象都满足协议。
- `Task.__lt__`（按 `due` 比较）是 `PriorityQueue` 正常工作的前提——没有 `due` 的任务会出错。
