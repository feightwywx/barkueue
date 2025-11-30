import asyncio
from typing import Any, Callable, Iterable, Awaitable, Sequence


class TaskType:
    def __init__(self, name: str, processor: Callable | None = None) -> None:
        self.name = name
        self.processor: Callable[..., Awaitable[Any]] | None = processor
        pass

    def init(self):
        pass

    def register_processor(self):
        pass


class Task:
    def __init__(self, id: str, task_type: TaskType, timestamp: int) -> None:
        self.id = id
        self.task_type = task_type
        self.timestamp = timestamp
        pass

    async def do(self):
        if self.task_type.processor is None:
            raise Exception("Processor not defined")
        return await self.task_type.processor()


class TaskQueue(asyncio.Queue[Task]):
    def __init__(self, name: str):
        self.name = name
        pass

    async def fetch(self):
        """
        Fetch task from database.
        """
        pass

    async def mark(self):
        """
        Mark task state in database.
        """
        pass


class Application:
    def __init__(self) -> None:
        self.queues: list[TaskQueue] = []
        self.task_types: dict[str, TaskType] = {}

    def init(self):
        pass

    def register_queue(self, queue: TaskQueue):
        self.queues.append(queue)

    def register_task_type(self, task: TaskType):
        self.task_types[task.name] = task

    async def worker(self, worker_id: int, queue: TaskQueue):
        while True:
            task = await queue.get()
            await task.do()
            queue.task_done()

    async def run(self):
        self.init()

        workers = [
            asyncio.create_task(self.worker(i, each))
            for i, each in enumerate(self.queues)
        ]

        try:
            # 运行一段时间
            await asyncio.sleep(10)
        finally:
            # 取消所有工作协程
            for worker in workers:
                worker.cancel()

        # 等待所有协程结束
        await asyncio.gather(*workers, return_exceptions=True)
