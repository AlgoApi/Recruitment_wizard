from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import logging
from .. import config

Base = declarative_base()
logger = logging.getLogger(__name__)

engine = create_async_engine(config.settings.database_url, future=True, echo=False, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    logger.info("init db")
    from ..models import form

    async with engine.begin() as conn:
        # Import models before create_all
        logger.info(Base.metadata.tables.keys())
        await conn.run_sync(Base.metadata.create_all)
