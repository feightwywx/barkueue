# barkueue

barkueue (*bark-queue*, or simply as *bark*), is a task queue designed to embed into a current business system, which is:

- Uses a relational database to storage business data
- Have no event processor, or event processor is hard to use for a simple case

It's **NOT** intended to:

- Act as a high performance and/or low latency task queue processing every transaction
- Replace the native external function or service broker of DBMS

## Usage

```python
import time

import barkueue as bark
from sqlalchemy import create_engine


ds = bark.datasource.SqlAlchemyDataSource(
    create_engine("mssql+pymssql://sa:Aa123456@172.22.47.52:14330")
)

app = bark.app([ds])


@app.handler("bark")
def bark_handler(app, task: bark.Task):
    print(f"{task.message} says: bark bark!")
    time.sleep(2)


@app.handler("woof")
def woof_handler(app, task):
    print(f"{task.message} says: woof woof!")
    time.sleep(3)


app.run()
```
