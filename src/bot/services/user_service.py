import logging
from typing import Optional
import asyncio

from sqlalchemy import select
from sqlalchemy.engine import ScalarResult
from sqlalchemy.exc import IntegrityError

from ..models.db import AsyncSessionLocal, DBManager
from ..models.form import UserModel

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager

    async def create_draft(self, user_id: int, username: str):
        # async with AsyncSessionLocal() as session:
        logger.info(f"create_draft {user_id}")

        user = UserModel(user_id=user_id, username=username)

        logger.debug(f"Draft {user_id} created {user.id}")
        return user

    async def submit_user(self, user: UserModel):
        if not getattr(user, "user_id", None):
            raise ValueError("user_id is required")
        if not getattr(user, "username", None):
            raise ValueError("username is required")

        logger.info(f"submit_user: id: {user.id} user_id: {user.user_id} username: {user.username}")

        async def work():
            async with self.db.session() as session:
                try:
                    async with session.begin():
                        session.add(user)
                        await session.flush()
                        new_id: Optional[int] = getattr(user, "id", None)
                        if new_id is None:
                            logger.error("failed submit user")
                            raise RuntimeError("Failed to obtain id after flush()")
                    await session.refresh(user)
                    await session.commit()
                    return user
                except IntegrityError:
                    session.rollback()
                    return None


        return await self.db.run(work, retries=3)

    async def get_last_id_from_db(self):
        logger.info(f"get_last_id_from_db")

        async def work():
            async with self.db.session() as session:
                stmt = select(UserModel.id).order_by(UserModel.id.desc()).limit(1)
                result = await session.execute(stmt)
                last_id = result.scalar_one_or_none()
                logger.debug(f"last_id: {last_id}")
                return last_id

        return await self.db.run(work, retries=3)

    async def get_user(self, user_entry_id: int = None, role: str = None, user_id: int = None, assigned_to: str = None,
                       limit: bool = True) -> UserModel | ScalarResult:
        logger.info(f"get_user: {user_entry_id}")

        async def work():
            async with self.db.session() as session:
                stmt = select(UserModel)
                if user_entry_id is not None:
                    logger.debug(f"user_entry_id: {user_entry_id}")
                    stmt = stmt.where(UserModel.id == user_entry_id)
                if role is not None:
                    logger.debug(f"role: {role}")
                    stmt = stmt.where(UserModel.role == role)
                if user_id is not None:
                    logger.debug(f"user_id: {user_id}")
                    stmt = stmt.where(UserModel.user_id == user_id)
                if assigned_to is not None:
                    logger.debug(f"assigned_to: {assigned_to}")
                    stmt = stmt.where(UserModel.assigned_to == assigned_to)

                stmt = stmt.order_by(UserModel.created_at)

                if limit:
                    stmt = stmt.limit(1)

                result = await session.execute(stmt)
                user = result.scalars()
                logger.debug(f"seccess get_user {user_entry_id}: {user.id if user else "None"}")

                if limit:
                    return user.first()
                else:
                    return user

        return await self.db.run(work, retries=3)

logger.info("HexUmaster IMPORTED")