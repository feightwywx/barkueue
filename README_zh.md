# barkueue

[English](README.md) | 简体中文

barkueue（读作 *bark-queue*，或简称为 *bark*），是一个设计用于嵌入已有业务系统的任务队列，适用于以下场景：

- 使用关系型数据库存储业务数据
- 没有事件处理器，或事件处理器对于简单场景而言过于复杂

它**不适用**于：

- 作为高性能和/或低延迟的任务队列处理每笔事务
- 替代数据库管理系统原生的外部函数或服务代理

## 样例

```python
import time

import barkueue as bark
from sqlalchemy import create_engine

arr = []
ds = bark.datasource.ArrayDataSource(arr)

app = bark.app([ds])


@app.handler("bark")
def bark_handler(app, task):
    print(f"{task.message} says: bark bark!")
    time.sleep(2)


@app.handler("woof")
def woof_handler(app, task):
    print(f"{task.message} says: woof woof!")
    time.sleep(3)


app.run()
```

## To-dos

- [x] fetch-consume 事件循环
- [x] fetch 间隔控制
- [x] 数据源diff，将状态更新合并到数据同步工作线程
- [x] 内存数据源
- [ ] 任务重试
- [ ] 事件系统（如 `@app.init`）
