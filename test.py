import time

from sqlalchemy import create_engine

import src as bark

ds = bark.datasource.SqlAlchemyDataSource(
    create_engine("mssql+pymssql://sa:Aa123456@172.22.47.52:14330")
)

app = bark.app([ds], max_workers=4, fetch_interval=5)


@app.handler("bark")
def bark_handler(app, task: bark.Task):
    print(f"{task.message} says: bark bark!")
    time.sleep(2)


@app.handler("woof")
def woof_handler(app, task):
    print(f"{task.message} says: woof woof!")
    time.sleep(3)


app.run()
