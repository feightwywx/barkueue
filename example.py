import time

import src as bark

arr: list[bark.Task] = [
    bark.Task("dog.bark", "Bluey"),
    bark.Task("dog.woof", "Bingo"),
    bark.Task("dog", "I'm *unicorse*, I like to eat children"),
]
ds = bark.datasource.ArrayDataSource(arr)

app = bark.app([ds], max_workers=4, fetch_interval=5)


@app.handler("dog.#")
def dog_handler(app: bark.Application, task: bark.Task) -> None:
    if task.message.find("*unicorse*") != -1:
        raise Exception(f"{task.message}")
    time.sleep(1)
    print(f"I'm {task.message}, a little puppy!")


@app.handler("dog.bark")
def bark_handler(app: bark.Application, task: bark.Task) -> None:
    time.sleep(3)
    print(f"{task.message} says: bark bark!")


@app.handler("dog.woof")
def woof_handler(app: bark.Application, task: bark.Task) -> None:
    time.sleep(2)
    print(f"{task.message} says: woof woof!")


app.run()
