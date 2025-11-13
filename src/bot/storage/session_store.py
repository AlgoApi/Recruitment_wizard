"""
Session store for FSM-like per-user conversation state.
Prefer Redis for horizontal scaling. A simple in-memory fallback is provided for dev.
"""
import json
import asyncio
from typing import Optional

import redis.asyncio as aioredis

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
        logger.info("connect to redis confirmed")

    async def get(self, user_id: int) -> dict[str, None | str | int | dict]:
        logger.info(f"redis get {user_id}")
        raw = await self._redis.get(f'session:{user_id}')
        return json.loads(raw) if raw else None

    async def get_other(self, key) -> dict[str, None | str | int | dict]:
        logger.info(f"redis other get {key}")
        raw = await self._redis.get(f'{key}')
        return json.loads(raw) if raw else None

    async def set_overwrite(self, user_id: int, value: dict, expire: int = 86400):
        logger.info(f"redis set overwrite{user_id}")
        logger.debug(f"redis set data: {json.dumps(value)}")
        await self._redis.set(f'session:{user_id}', json.dumps(value), ex=expire, xx=True)

    async def set_initialize(self, user_id: int, value: dict, expire: int = 86400):
        await self._redis.ping()
        logger.info(f"redis set init {user_id}")
        logger.debug(f"redis set data: {json.dumps(value)}")
        await self._redis.set(f'session:{user_id}', json.dumps(value), ex=expire, nx=True)

    async def set_other(self, key, value, nx:Optional[bool]=False, ex:int=60*30, xx:Optional[bool]=False):
        logger.info(f"redis set other {key}")
        logger.debug(f"redis set data: {value}")
        return await self._redis.set(key, value, ex=ex, nx=nx, xx=xx)

    async def pop(self, user_id: int):
        logger.info(f"redis pop {user_id}")
        val = await self.get(user_id)
        logger.info(f"redis _delete")
        await self._redis.delete(f'session:{user_id}')
        await self._redis
        return val

    async def pop_other(self, key):
        logger.info(f"redis other pop {key}")
        val = await self.get_other(key)
        logger.info(f"redis _delete")
        await self._redis.delete(f'{key}')
        await self._redis
        return val

    async def del_other(self, key:str):
        logger.info(f"redis delete other {key}")
        await self._redis.delete(key)
        await self._redis

async def create_session_store():
    if settings.redis_url and aioredis:
        s = RedisSessionStore(settings.redis_url)
        await s.connect()
        logger.info('Connected to redis session store')
        return s
    else:
        logger.critical('Redis not configured or aioredis missing')
        raise RuntimeError("Redis not configured or aioredis missing")

logger.info("Runecaster IMPORTED")