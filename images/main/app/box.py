from box_sdk_gen import BoxClient, BoxCCGAuth, CCGConfig
from box_ai_agents_toolkit import box_file_text_extract

from asyncio import create_task, sleep, to_thread, Future, Lock, Queue
from os import environ
from random import uniform
from time import monotonic


class Box:
    _patched_connection_pool = False

    def __init__(
        self,
        rate_limit: int = 100,
        rate_limit_window_in_seconds: int = 60,
        number_of_extractors: int = 100,
        jitter_in_seconds: float = 1,
    ):
        self.client = BoxClient(
            auth=BoxCCGAuth(
                config=CCGConfig(
                    client_id=environ["BOX_CLIENT_ID"],
                    client_secret=environ["BOX_CLIENT_SECRET"],
                    enterprise_id=environ["BOX_ENTERPRISE_ID"],
                )
            )
        )
        self.jitter_in_seconds = jitter_in_seconds
        self.rate_limiter = RateLimiter(rate_limit, rate_limit_window_in_seconds)
        self.queue = Queue()
        self.extractors = [
            create_task(self.extractor()) for _ in range(number_of_extractors)
        ]

        if not Box._patched_connection_pool:
            patch_connection_pool(maxsize=number_of_extractors)
            Box._patched_connection_pool = True

    async def extract(self, file: str) -> str:
        for attempt in range(3):
            try:
                f = Future()
                await self.queue.put((file, f))
                return await f
            except Exception as e:
                if attempt == 2:
                    raise e

                status_code = e.response_info.status_code
                if status_code != 429:
                    raise e

                retry_after = e.response_info.headers.get("retry-after", 60)
                await sleep(retry_after)

    async def extractor(self):
        while True:
            file, f = await self.queue.get()
            try:
                await self.rate_limiter.throttle()
                await sleep(uniform(0, self.jitter_in_seconds))
                result = await to_thread(box_file_text_extract, self.client, file)
                f.set_result(result)
            except Exception as e:
                f.set_exception(e)
            finally:
                self.queue.task_done()


class RateLimiter:
    def __init__(self, rate_limit: int, rate_limit_window_in_seconds: int):
        self.rate_limit = rate_limit
        self.rate_limit_window_in_seconds = rate_limit_window_in_seconds
        self.lock = Lock()
        self.request_count = 0
        self.window_start = monotonic()

    async def throttle(self):
        while True:
            async with self.lock:
                now = monotonic()
                elapsed = now - self.window_start
                if elapsed >= self.rate_limit_window_in_seconds:
                    self.window_start = now
                    self.request_count = 0

                if self.request_count < self.rate_limit:
                    self.request_count += 1
                    return
                else:
                    wait_time = self.rate_limit_window_in_seconds - elapsed
            await sleep(wait_time)


def patch_connection_pool(**constructor_kwargs):
    from urllib3 import connectionpool, poolmanager

    class ConnectionPool(connectionpool.HTTPSConnectionPool):
        def __init__(self, *args, **kwargs):
            kwargs.update(constructor_kwargs)
            super(ConnectionPool, self).__init__(*args, **kwargs)

    poolmanager.pool_classes_by_scheme["https"] = ConnectionPool
