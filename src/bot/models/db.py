from sqlalchemy.orm import declarative_base, Session
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Callable, Coroutine, Optional, TypeVar, AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError, DBAPIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
import logging
from .. import config

Base = declarative_base()
logger = logging.getLogger(__name__)
T = TypeVar("T")

def make_engine(database_url: str):
    return create_async_engine(
        database_url,
        future=True,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_timeout=30,
    )

class DBManager:
    def __init__(self, database_url: str):
        self._database_url = database_url
        self._engine = make_engine(database_url)
        self._SessionLocal = sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)
        self._recreate_lock = asyncio.Lock()  # serialize recreations
        self._recreate_cooldown = 5
        self._last_recreate: float = 0.0

    async def init_db(self):
        logger.info("init db")
        from ..models import form

        async with self._engine.begin() as conn:
            # Import models before create_all
            logger.info(Base.metadata.tables.keys())
            await conn.run_sync(Base.metadata.create_all)

    @property
    def engine(self):
        return self._engine

    @property
    def SessionLocal(self):
        return self._SessionLocal

    # context manager to get session
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[Session, Any]:
        """
        Usage:
            async with db_manager.session() as session:
                await session.execute(...)
        Guarantees session.close() called at the end.
        """
        sess = self._SessionLocal()
        try:
            yield sess
        finally:
            await sess.close()

    # async helper to dispose and recreate engine/pool (safe)
    async def dispose_and_recreate_engine(self) -> None:
        # serialize recreations
        async with self._recreate_lock:
            import time
            now = time.time()
            if now - self._last_recreate < self._recreate_cooldown:
                # someone недавно пересоздал — короткий cooldown
                logger.info("Recent recreate happened, skipping another recreation")
                return
            logger.warning("Disposing and recreating DB engine/pool")
            try:
                # async dispose
                await self._engine.dispose()
            except Exception:
                logger.exception("Error disposing old engine")

            # create new engine and sessionmaker
            try:
                self._engine = make_engine(self._database_url)
                self._SessionLocal = sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)
                self._last_recreate = now
                logger.info("DB engine recreated successfully")
            except Exception:
                logger.exception("Failed to recreate engine")
                raise

    # Асинхронный retry-декоратор с tenacity
    def retry_decorator(self, stop_after=3):
        return retry(
            reraise=True,
            stop=stop_after_attempt(stop_after),
            wait=wait_exponential(multiplier=0.5, min=1, max=10),
            retry=retry_if_exception_type((OperationalError, DBAPIError, RuntimeError)),
        )

    async def run(self, coro_factory: Callable[[], Coroutine[Any, Any, T]], *, retries: int = 3) -> T:
        """
        coro_factory: callable returning coroutine which will perform DB work.
        Example:
           await db.run(lambda: session.execute(stmt))
        """
        # создаём декоратор на лету (tenacity async)
        dec = self.retry_decorator(stop_after=retries)

        @dec
        async def _wrapped():
            # IMPORTANT: coro_factory must create its own session inside, or else you'd reuse closed sessions across retries.
            return await coro_factory()

        try:
            result = await _wrapped()
            return result
        except RetryError as re:
            logger.exception("All retry attempts failed; will attempt to recreate engine and retry once more")
            try:
                await self.dispose_and_recreate_engine()
            except Exception:
                logger.exception("Recreate failed")
                raise
            return await coro_factory()

AsyncSessionLocal = DBManager(database_url=config.settings.database_url)
