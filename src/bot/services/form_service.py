from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Optional, Dict, Any, Coroutine, List
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text, desc

from ..models.db import AsyncSessionLocal
from ..models.form import FormModel
from ..security.security_rules import MODER_USERNAMES

logger = logging.getLogger(__name__)

MV_USER_SQL = text("""
SELECT assigned_to, role, status, week_count, month_count, year_count
FROM mv_forms_stats_by_user
WHERE assigned_to = :username;
""")


class FormService:
    def __init__(self):
        self._sigma = -1

    async def create_draft(self, user_id: int, username: str, role: str, content: dict):
        # async with AsyncSessionLocal() as session:
        users = list(MODER_USERNAMES.values())
        if self._sigma < 0:
            last_id = await self.get_last_id_from_db()
            if not last_id:
                last_id = 0
            if last_id & 1 == 0:
                self._sigma = 0
            else:
                if 1 < len(sorted(users)):
                    self._sigma = 1
        if self._sigma >= len(sorted(users)):
            self._sigma = 0

        form = FormModel(user_id=user_id, username=username,
                         role=role, content=content, status=None,
                         assigned_to=sorted(users)[self._sigma])

        self._sigma += 1
        # session.add(form)
        # await session.commit()
        # await session.refresh(form)
        logger.debug('Draft created %s', form.id)
        return form

    async def update_form(self, form_id: int, content: dict | None = None, status: bool | None = None):
        values = {}
        if content is not None:
            values["content"] = content
        if status is not None:
            values["status"] = status

        if not values:
            return None  # ничего обновлять

        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = update(FormModel).where(FormModel.id == form_id).values(**values).execution_options(
                    synchronize_session="fetch")
                res = await session.execute(stmt)
                if res.rowcount == 0:
                    return None
                # При необходимости: вернуть актуальную запись
                result = await session.execute(select(FormModel).where(FormModel.id == form_id))
                return result.scalars().first()

    async def submit_form(self, form: FormModel):
        if not getattr(form, "user_id", None):
            raise ValueError("user_id is required")
        if not getattr(form, "username", None):
            raise ValueError("username is required")
        if not getattr(form, "role", None):
            raise ValueError("role is required")

        content = form.content or {}
        try:
            json.dumps(content)
        except (TypeError, ValueError) as e:
            raise ValueError("content must be JSON-serializable") from e

        # 2. вставляем и получаем id через flush()
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(form)
                await session.flush()
                new_id: Optional[int] = getattr(form, "id", None)
                if new_id is None:
                    raise RuntimeError("Failed to obtain id after flush()")
            await session.refresh(form)
            await session.commit()
        return form

    async def get_last_id_from_db(self):
        async with AsyncSessionLocal() as session:
            stmt = select(FormModel.id).order_by(FormModel.id.desc()).limit(1)
            result = await session.execute(stmt)
            last_id = result.scalar_one_or_none()
            return last_id

    async def get_form(self, form_id: int = None, role: str = None, user_id: int = None, assigned_to: str = None, status:bool = None) -> FormModel:
        async with AsyncSessionLocal() as session:
            if status is not None:
                stmt = select(FormModel).where(FormModel.status.is_not(None))
            else:
                stmt = select(FormModel).where(FormModel.status.is_(None))
            if form_id is not None:
                stmt = stmt.where(FormModel.id == form_id)
            if role is not None:
                stmt = stmt.where(FormModel.role == role)
            if user_id is not None:
                stmt = stmt.where(FormModel.user_id == user_id)
            if assigned_to is not None:
                stmt = stmt.where(FormModel.assigned_to == assigned_to)

            stmt = stmt.order_by(FormModel.created_at).limit(1)

            result = await session.execute(stmt)
            form = result.scalars().first()
            return form

    async def is_cooldown(self, user_id: int, role: str, hours: int = 1) -> int:
        stmt = (
            select(FormModel.created_at)
            .where(FormModel.status.is_(False))
            .where(FormModel.user_id == user_id)
            .where(FormModel.role == role)
            .order_by(desc(FormModel.created_at))
            .limit(1)
        )

        async with AsyncSessionLocal() as session:
            result = await session.execute(stmt)
            created_at = result.scalar_one_or_none()  # datetime или None

        if created_at is None:
            return 0

        now = datetime.now(timezone.utc)

        expiry = created_at + timedelta(hours=hours)
        remaining_seconds = (expiry - now).total_seconds()

        if remaining_seconds <= 0:
            return 0

        # округляем вверх до целых минут
        return int(remaining_seconds - 1) // 60 + 1

    async def is_submited(self, user_id: int, role: str) -> bool:
        async with (AsyncSessionLocal() as session):
            stmt = select(FormModel).where(FormModel.status.is_(None)
                                           ).where(FormModel.user_id == user_id).where(FormModel.role == role).limit(1)

            result = await session.execute(stmt)
            form = result.scalars().first()
            return True if form else False

    # Асинхронная функция получения статистики
    async def get_forms_stats(
            self,
            assigned_to: Optional[str] = None,
            period: Optional[str] = None,
            tz: str = "UTC",
    ) -> dict[str, dict[str, int]]:
        """
        Возвращает числа за последние 7, 30 и 365 дней, разбитые по role (agent/operator)
        и по status (None/False/True).

        assigned_to: если None — все, иначе — фильтруем assigned_to = :assigned_to
        """
        def _get_query():
            return f"""
            SELECT
              SUM(CASE WHEN (created_at AT TIME ZONE 'UTC') >= (date_trunc('day', now() AT TIME ZONE 'UTC') - interval '{period}') AND role = 'agent'    AND status IS NULL  THEN 1 ELSE 0 END) AS agent_none,
              SUM(CASE WHEN (created_at AT TIME ZONE 'UTC') >= (date_trunc('day', now() AT TIME ZONE 'UTC') - interval '{period}') AND role = 'agent'    AND status IS FALSE THEN 1 ELSE 0 END) AS agent_false,
              SUM(CASE WHEN (created_at AT TIME ZONE 'UTC') >= (date_trunc('day', now() AT TIME ZONE 'UTC') - interval '{period}') AND role = 'agent'    AND status IS TRUE  THEN 1 ELSE 0 END) AS agent_true,
              SUM(CASE WHEN (created_at AT TIME ZONE 'UTC') >= (date_trunc('day', now() AT TIME ZONE 'UTC') - interval '{period}') AND role = 'operator' AND status IS NULL  THEN 1 ELSE 0 END) AS operator_none,
              SUM(CASE WHEN (created_at AT TIME ZONE 'UTC') >= (date_trunc('day', now() AT TIME ZONE 'UTC') - interval '{period}') AND role = 'operator' AND status IS FALSE THEN 1 ELSE 0 END) AS operator_false,
              SUM(CASE WHEN (created_at AT TIME ZONE 'UTC') >= (date_trunc('day', now() AT TIME ZONE 'UTC') - interval '{period}') AND role = 'operator' AND status IS TRUE  THEN 1 ELSE 0 END) AS operator_true
              
            FROM "Recruitment_forms"{f" WHERE (assigned_to = '{assigned_to}')" if assigned_to is not None else ''};
            """

        async def _exec_and_format():
            def _val(name: str, row) -> int:
                v = row[name] if row is not None else None
                return int(v) if v is not None else 0
            async with AsyncSessionLocal() as session:
                result = await session.execute(text(_get_query()), {"assigned_to": assigned_to, "tz": tz})
                row = result.fetchone()
            out = {
                "agent": {
                    "none": _val(f"agent_none", row),
                    "false": _val(f"agent_false", row),
                    "true": _val(f"agent_true", row),
                },
                "operator": {
                    "none": _val(f"operator_none", row),
                    "false": _val(f"operator_false", row),
                    "true": _val(f"operator_true", row),
                },
            }
            return out

        # helper to read column safely and cast to int

        res = await asyncio.gather(_exec_and_format())

        return res

