import logging
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.engine import ScalarResult
from sqlalchemy.exc import IntegrityError

from ..models.db import DBManager
from ..models.form import StaffModel

logger = logging.getLogger(__name__)


class StaffService:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager

    async def create_draft(self, username: str, role: str, assigned_to:str, actual:bool):
        # async with AsyncSessionLocal() as session:
        logger.info(f"create_draft staff {username}")

        staff = StaffModel(username=username, role=role, assigned_to=assigned_to, actual=actual)

        logger.debug(f"Draft staff {username} created {staff.id}")
        return staff

    async def submit_staff(self, staff: StaffModel):
        if not getattr(staff, "user_id", None):
            raise ValueError("user_id is required")
        if not getattr(staff, "username", None):
            raise ValueError("username is required")

        logger.info(f"submit_user: id: {staff.id} user_id: {staff.user_id} username: {staff.username}")

        async def work():
            async with self.db.session() as session:
                try:
                    async with session.begin():
                        session.add(staff)
                        await session.flush()
                        new_id: Optional[int] = getattr(staff, "id", None)
                        if new_id is None:
                            logger.error("failed submit staff")
                            raise RuntimeError("Failed to obtain id after flush()")
                    await session.refresh(staff)
                    await session.commit()
                    return staff
                except IntegrityError:
                    await session.rollback()
                    return None


        return await self.db.run(work, retries=3)

    async def get_last_id_from_db(self):
        logger.info(f"get_last_id_from_db")

        async def work():
            async with self.db.session() as session:
                stmt = select(StaffModel.id).order_by(StaffModel.id.desc()).limit(1)
                result = await session.execute(stmt)
                last_id = result.scalar_one_or_none()
                logger.debug(f"last_id: {last_id}")
                return last_id

        return await self.db.run(work, retries=3)

    async def get_staff(self, staff_entry_id: int = None, role: str = None, username: str = None, assigned_to: str = None,
                       limit: bool = True, actual:bool=True) -> StaffModel | ScalarResult:
        logger.info(f"get_staff: {staff_entry_id}")

        async def work():
            async with self.db.session() as session:
                stmt = select(StaffModel)
                if staff_entry_id is not None:
                    logger.debug(f"staff_entry_id: {staff_entry_id}")
                    stmt = stmt.where(StaffModel.id == staff_entry_id)
                if role is not None:
                    logger.debug(f"role: {role}")
                    stmt = stmt.where(StaffModel.role == role)
                if username is not None:
                    logger.debug(f"username: {username}")
                    stmt = stmt.where(StaffModel.username == username)
                if assigned_to is not None:
                    logger.debug(f"assigned_to: {assigned_to}")
                    stmt = stmt.where(StaffModel.assigned_to == assigned_to)

                stmt = stmt.where(StaffModel.actual == actual).order_by(StaffModel.id)

                if limit:
                    stmt = stmt.limit(1)

                result = await session.execute(stmt)
                staff = result.scalars()

                if limit:
                    staff = staff.first()
                    logger.debug(f"success get_staff {staff_entry_id}: {staff.id if staff else "None"}")
                    return staff
                else:
                    if staff is not None:
                        logger.debug(f"success get_staff {staff_entry_id}")
                    else:
                        logger.error(f"error get_staff {staff_entry_id} staff is none")
                    return staff

        return await self.db.run(work, retries=3)

    async def update_form(self, find_username: str|None=None, find_role:str="moderator", find_assigned_to:str|None=None, find_actual: bool = True, actual: bool | None = None, agent_need: bool | None = None, operator_need: bool | None = None):
        values = {}
        if actual is not None:
            values["actual"] = actual
        if agent_need is not None:
            values["agent_need"] = agent_need
        if operator_need is not None:
            values["operator_need"] = operator_need

        if not values:
            logger.debug(f"nothing to update")
            return None

        logger.info(f"update_form: {find_username}|{find_assigned_to}")
        logger.debug(f"update_form {find_username}|{find_assigned_to}: content: {actual}|{agent_need}|{operator_need}")

        async def work():
            async with self.db.session() as session:
                async with session.begin():
                    stmt = update(StaffModel).where(StaffModel.username == find_username).where(StaffModel.actual == find_actual)
                    if find_assigned_to:
                        stmt = stmt.where(StaffModel.assigned_to == find_assigned_to)
                    if find_role:
                        stmt = stmt.where(StaffModel.role == find_role)
                    stmt = stmt.values(**values).execution_options(synchronize_session="fetch")
                    res = await session.execute(stmt)
                    if res.rowcount == 0:
                        return None
                    # вернуть актуальную запись
                    stmt_res = select(StaffModel).where(StaffModel.username == find_username).where(StaffModel.actual == find_actual)
                    if find_assigned_to:
                        stmt_res = stmt.where(StaffModel.assigned_to == find_assigned_to)
                    if find_role:
                        stmt_res = stmt.where(StaffModel.role == find_role)
                    result = await session.execute(stmt_res)
                    return result.scalars().first()

        return await self.db.run(work, retries=3)

logger.info("HexUmaster IMPORTED")