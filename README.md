# barkueue

barkueue (*bark-queue*, or simply as *bark*), is a task queue designed to embed into a current business system, which is:

- Uses a relational database to storage business data
- Have no event processor, or event processor is hard to use for a simple case

It's **NOT** intended to:

- Act as a high performance and/or low latency task queue processing every transaction
- Replace the native external function or service broker of DBMS

## Usage

(WIP, pseudo code)

```python
import barkueue as bark

# create a app instance
app = bark.app(db_connection, loop_interval=1000)

# create a queue
queue = bark.queue("main")

# init queue table structure and other things
@queue.init
def init_main_queue():
    ...

# register queue to app
app.register_queue(queue)

# create a task
task = bark.task("say_bark")

# init task triggers and other things
@task.init
def init_say_bark_task():
    ...

# define the task processor
@task.processor
def say_bark():
    print("Bark Bark!")

# register task to app
app.register_task(task)

# run app
app.run()
```
