import time

from sqlalchemy import create_engine

from src.Application import Application
from src.Queue import Queue

app = Application(create_engine('mssql+pymssql://sa:Aa123456@172.22.47.52:14330'))

q1 = Queue('q1', minFetchInterval=1)
q1.bind(app)

q2 = Queue('q2', minFetchInterval=1)
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
