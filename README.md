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

from sqlalchemy import create_engine

from barkueue.Application import Application
from barkueue.Queue import Queue

app = Application(create_engine('mssql+pymssql://sa:Aa123456@172.22.47.52:14330'))

q1 = Queue('q1')
q1.bind(app)

q2 = Queue('q2')
q2.bind(app)

@app.register_exec('e1')
def e1(_):
    print('hello e1')
    time.sleep(2)

@app.register_exec('e2')
def e2(_):
    print('hello e2')
    time.sleep(3)

app.run()
```
