"""
Session store for FSM-like per-user conversation state.
Prefer Redis for horizontal scaling. A simple in-memory fallback is provided for dev.
"""
import json
import asyncio

import aioredis

from ..config import settings
import logging
logger = logging.getLogger(__name__)

class RedisSessionStore:
    def __init__(self, url: str):
        if not aioredis:
            raise RuntimeError('aioredis is required for RedisSessionStore')
        self._redis = None
        self.url = url

    async def connect(self):
        self._redis = await aioredis.from_url(self.url, encoding='utf-8', decode_responses=True)
        for _ in range(3):
            try:
                await self._redis.ping()
                govno = await self._redis.set("__warmup__", "1", ex=5)
                logger.info(f"test return value for redis set: {type(govno)}")
                if type(govno) is not bool:
                    logger.error("FAILED, is mast be bool")
                break
            except Exception as e:
                logging.warning("Redis warmup failed, retrying: %s", e)
                await asyncio.sleep(0.2)

    async def get(self, user_id: int) -> dict[str, None | str | int | dict]:
        raw = await self._redis.get(f'session:{user_id}')
        return json.loads(raw) if raw else None

    async def set_overwrite(self, user_id: int, value: dict, expire: int = 86400):
        await self._redis.set(f'session:{user_id}', json.dumps(value), ex=expire, xx=True)

    async def set_initialize(self, user_id: int, value: dict, expire: int = 86400):
        await self._redis.ping()
        await self._redis.set(f'session:{user_id}', json.dumps(value), ex=expire, nx=True)

    async def set_other(self, key, value, nx=None, ex:int=60*30):
        await self._redis.set(key, value, ex=ex, nx=nx)

    async def pop(self, user_id: int):
        val = await self.get(user_id)
        await self._redis.delete(f'session:{user_id}')
        await self._redis
        return val

class MemorySessionStore:
    def __init__(self):
        self._store = {}
        self._lock = asyncio.Lock()

    async def connect(self):
        return

    async def get(self, user_id: int):
        async with self._lock:
            return self._store.get(user_id)

    async def set(self, user_id: int, value: dict):
        async with self._lock:
            self._store[user_id] = value

    async def pop(self, user_id: int):
        async with self._lock:
            return self._store.pop(user_id, None)

async def create_session_store():
    if settings.redis_url and aioredis:
        s = RedisSessionStore(settings.redis_url)
        await s.connect()
        logger.info('Connected to redis session store')
        return s
    else:
        logger.warning('Redis not configured or aioredis missing, using in-memory sessions PERFORMANCE LOSS!!')
        s = MemorySessionStore()
        await s.connect()
        return s
