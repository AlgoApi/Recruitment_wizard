from typing import Sequence, Optional, List

from pyrogram.types import InlineKeyboardButton

from ..forms.definition import FormDefinition
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from pyrogram.raw import types as raw_types

from ..services.staff_service import StaffService

MOSCOW = ZoneInfo("Europe/Moscow")
logger = logging.getLogger(__name__)

class FormConversation:
    def __init__(self, form_def: FormDefinition):
        self.form_def = form_def


def format_content(content: dict, form_conv: FormConversation, indent: int = 0) -> str:
    logger.info("Formatting dict")
    logger.debug(f"dict content: {content}")
    pad = " " * indent
    lines: list[str] = []
    if isinstance(content, dict):
        for k, v in content.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{translate_fields(k, form_conv)}:")
                lines.append(format_content(v, indent=indent + 2, form_conv=form_conv))
            else:
                lines.append(f"{pad}{translate_fields(k, form_conv)}: {v}")
    elif isinstance(content, list):
        for i, v in enumerate(content, 1):
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}- [{i}]")
                lines.append(format_content(v, indent=indent + 2, form_conv=form_conv))
            else:
                lines.append(f"{pad}- {v}")
    else:
        lines.append(f"{pad}{content}")
    return "\n".join(lines)


def translate_fields(key:str, form_conv: FormConversation):
    logger.info("Translating fields")
    fields = form_conv.form_def.fields
    for field in fields:
        if field.key == key:
            return field.label
    return key

def translate_role(txt:str) -> str:
    logger.info("Manual translating role")
    match txt:
        case "agent":
            return "агента"
        case "operator":
            return "оператора"
    return ""

def stat_text_gen(data:dict[str, dict[str, int]] | list) -> str:
    logger.info("Generating text stats")
    if type(data) is list:
        data = data[0]
    return (f"\tОжидающие анкеты оператора: {data.get("operator", {}).get("none")}\n"
    f"\tПринятые анкеты оператора: {data.get("operator", {}).get("true")}\n"
    f"\tОтклонённые анкеты оператора: {data.get("operator", {}).get("false")}\n"
    "\n"
    f"\tОжидающие анкеты агента: {data.get("agent", {}).get("none")}\n"
    f"\tПринятые анкеты агента: {data.get("agent", {}).get("true")}\n"
    f"\tОтклонённые анкеты агента: {data.get("agent", {}).get("false")}\n")

def ensure_aware_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def remaining_seconds_moscow(created_at, hours):
    """
    created_at: datetime (naive or aware)
    hours: int/float
    Возвращает количество секунд до expiry, считая времена в московской зоне.
    """
    # 1) Сделать created_at aware в зоне Moscow если он naive
    if created_at is None:
        return None

    if created_at.tzinfo is None:
        # интерпретируем stored time как московское локальное время
        created_at_msk = created_at.replace(tzinfo=MOSCOW)
    else:
        # если already aware — привести к Moscow
        created_at_msk = created_at.astimezone(MOSCOW)

    # 2) now в Moscow
    now_msk = datetime.now(MOSCOW)

    # 3) expiry и remaining
    expiry = created_at_msk + timedelta(hours=hours)
    remaining = (expiry - now_msk).total_seconds()

    return remaining

async def make_raw_reply_markup(kb: Sequence[Sequence[InlineKeyboardButton]]):
    rows = []
    for row in kb:
        raw_buttons = []
        for btn in row:
            if not isinstance(btn.callback_data, (bytes, bytearray)):
                data = (btn.callback_data or "").encode("utf-8")
            else:
                data = btn.callback_data
            raw_buttons.append(raw_types.KeyboardButtonCallback(text=btn.text, data=data))
        rows.append(raw_types.KeyboardButtonRow(buttons=raw_buttons))
    return raw_types.ReplyInlineMarkup(rows=rows)

async def assign_master(staff_service: StaffService, role:str, user_id):
    assigned = "NOT ASSIGNED"
    staffs = await staff_service.get_staff(role="moderator", limit=False)
    for staff_entry in staffs:
        if role == "operator":
            # TEMP business
            #if staff_entry.operator_need:
            #    assigned = staff_entry.username
            assigned = "hr_artemiy"
        elif role == "agent":
            if staff_entry.agent_need:
                assigned = staff_entry.username
        else:
            logger.error(f"sigma {user_id}: {assigned} staffs is not None")

    if assigned == "NOT ASSIGNED":
        if role == "operator":
            await staff_service.update_form(find_role="moderator", operator_need=True)
        elif role == "agent":
            await staff_service.update_form(find_role="moderator", agent_need=True)
        logger.info(f"empty sigma {user_id}: {assigned} recycle moderators")
        staffs = await staff_service.get_staff(role="moderator", limit=False)
        for staff_entry in staffs:
            if role == "operator":
                # TEMP business
                # if staff_entry.operator_need:
                #    assigned = staff_entry.username
                assigned = "hr_artemiy"
            elif role == "agent":
                if staff_entry.agent_need:
                    assigned = staff_entry.username
            else:
                logger.error(f"sigma {user_id}: {assigned} staffs is not None")

    if assigned == "NOT ASSIGNED":
        logger.error(f"EMPTY sigma {user_id}: {assigned}")
        assigned = None

    return assigned
