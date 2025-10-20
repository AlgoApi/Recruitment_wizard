import asyncio
import logging
import uvloop
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from .models.db import init_db
from .utils.busines_text import hello_message, cooldown_text
from .utils.utils import format_content
from .config import settings
from .logging_config import setup_logging
from .storage.session_store import create_session_store
from .handlers.form_handler import FormConversation
from .services.form_service import FormService
from .handlers.callbacks import callback_router, callback_global_router
from .forms.definition import operator_form, agent_form
from .security.security_rules import allowed_admin_rule, ADMIN_USERNAMES
from .security.security_rules import allowed_moder_rule, MODER_USERNAMES
from .security.security_rules import allowed_superadmin_rule

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

ALL_CMDS = ["start", "help", "fill", "whoami", "del_admin", "del_moderator", "add_admin", "add_moderator"]

def getter_setter_admitted_users_wizard(path: str,
                      encoding: str = "utf-8", write: bool = False, overwrite: bool = False, data: str = None, _try: bool = False) -> set|None:
    result = set()
    if write:
        with open(path, "a", encoding=encoding, errors="replace") as f:
            f.write(data)
        return None
    elif overwrite:
        with open(path, "w", encoding=encoding, errors="replace") as f:
            f.write(data)
        return None
    else:
        try:
            with open(path, "r", encoding=encoding, errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line == "":
                        continue
                    result.add(line)
        except FileNotFoundError:
            if not _try:
                return getter_setter_admitted_users_wizard(path, encoding, write, overwrite, data, True)
    return result

async def run_wizard():
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logging.getLogger("redis").setLevel(logging.DEBUG)

    await init_db()

    MODER_USERNAMES.update(getter_setter_admitted_users_wizard("moders.txt"))
    ADMIN_USERNAMES.update(getter_setter_admitted_users_wizard("admins.txt"))

    session_store = await create_session_store()
    form_service = FormService()

    app = Client('Recruitment-SOD', bot_token=settings.bot_token, api_id=settings.api_id, api_hash=settings.api_hash)

    operator_form_conv = FormConversation(session_store, form_service, operator_form)
    agent_form_conv = FormConversation(session_store, form_service, agent_form)

    @app.on_message(filters.command(['start', 'help']) & filters.private)
    async def cmd_start(client: Client, message: Message):
        text = ""
        if message.from_user.username in ADMIN_USERNAMES:
            text += '/add_moderator <username>(без собачки) - Добавить права менеджера пользователю\n'
            text += '/del_moderator <username>(без собачки) - Удалить права менеджера у пользователя\n'
            text += '/del_admin <username>(без собачки) - Удалить права админа у пользователя\n'
        if message.from_user.username == settings.superadmin_username.lower():
            text += '/add_admin <username>(без собачки) - Добавить права админа пользователю\n'
        if message.from_user.username in MODER_USERNAMES:
            text += '/del_moderator <username>(без собачки) - Удалить права менеджера у пользователя\n'
            text += '/view - Просмотр пришедших анкет\n'
            text += '/stat[7/30/365] - Просмотр общей статистики за столько-то дней\n'
            text += '/xll[7/30/365] - Просмотр личной статистики за столько-то дней\n'
        text += hello_message

        kb = [
            [
                InlineKeyboardButton("Оператор", callback_data=f"operator:start"),
                InlineKeyboardButton("Агент", callback_data=f"agent:start"),
                InlineKeyboardButton("Информация", callback_data=f"info:info"),
            ]
        ]

        await message.reply(text, reply_markup=InlineKeyboardMarkup(kb))
    '''
    DEPRECATED
    @app.on_message(filters.command(['fill']) & filters.private)
    async def cmd_fill(client: Client, message: Message):
        await operator_form_conv.start(client, message)
    '''

    @app.on_message(filters.command(['add_moderator']) & filters.private & allowed_admin_rule)
    async def cmd_add_moder(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            getter_setter_admitted_users_wizard("moders.txt", write=True, data=text_after_command)
            MODER_USERNAMES.add(text_after_command)
            text = f"Модераторов теперь: {len(MODER_USERNAMES)}\n"
            for nick in list(MODER_USERNAMES):
                text += nick[:3] + "\n"
            await message.reply(text)
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['add_admin']) & filters.private & allowed_superadmin_rule)
    async def cmd_add_admin(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            getter_setter_admitted_users_wizard("admin.txt", write=True, data=text_after_command)
            ADMIN_USERNAMES.add(text_after_command)
            text = f"Админов теперь: {len(ADMIN_USERNAMES)}\n"
            for nick in list(ADMIN_USERNAMES):
                text += nick[:3] + "\n"
            await message.reply(text)
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['del_moderator']) & filters.private & (allowed_moder_rule | allowed_admin_rule))
    async def cmd_del_moder(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            if text_after_command in MODER_USERNAMES:
                if message.from_user.username == text_after_command or message.from_user.username == ADMIN_USERNAMES:
                    MODER_USERNAMES.discard(text_after_command)
                    text = f"Модераторов теперь: {len(MODER_USERNAMES)}\n"
                    for nick in list(MODER_USERNAMES):
                        text += nick[:3] + "\n"
                    await message.reply(text)
                    getter_setter_admitted_users_wizard("moders.txt", overwrite=True, data="\n".join(MODER_USERNAMES))
                else:
                    await message.reply("Ты можешь отправить в отставку только себя")
            else:
                await message.reply("Уже в отставке")
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['del_admin']) & filters.private & allowed_superadmin_rule)
    async def cmd_del_admin(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            if text_after_command in ADMIN_USERNAMES:
                if message.from_user.username == text_after_command or message.from_user.username == settings.superadmin_username:
                    ADMIN_USERNAMES.discard(text_after_command)
                    text = f"Админов теперь: {len(ADMIN_USERNAMES)}\n"
                    for nick in list(ADMIN_USERNAMES):
                        text += nick[:3] + "\n"
                    await message.reply(text)
                    getter_setter_admitted_users_wizard("admin.txt", overwrite=True, data="\n".join(ADMIN_USERNAMES))
                else:
                    await message.reply("Ты можешь отправить в отставку только себя")
            else:
                await message.reply("Уже в отставке")
        else:
            await message.reply("В следующий раз напиши username после команды")


    @app.on_message(filters.command("stat7") & filters.private & allowed_moder_rule)
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_stat()
        text = ("Общая статистика заявок:\n"
                "за послдение 7 дней:\n"
                f"\tОжидающие анкеты оператора: {data.get("operator_pending_week")}\n"
                f"\tПринятые анкеты оператора: {data.get("operator_accepted_week")}\n"
                f"\tОтклонённые анкеты оператора: {data.get("operator_rejected_week")}\n"
                "\n"
                f"\tОжидающие анкеты агента: {data.get("agent_pending_week")}\n"
                f"\tПринятые анкеты агента: {data.get("agent_accepted_week")}\n"
                f"\tОтклонённые анкеты агента: {data.get("agent_rejected_week")}\n"
                )
        await message.reply(text)

    @app.on_message(filters.command("stat30") & filters.private & allowed_moder_rule)
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_stat()
        text = ("Общая статистика заявок:\n"
                "за послдение 30 дней:\n"
                f"\tОжидающие анкеты оператора: {data.get("operator_pending_month")}\n"
                f"\tПринятые анкеты оператора: {data.get("operator_accepted_month")}\n"
                f"\tОтклонённые анкеты оператора: {data.get("operator_rejected_month")}\n"
                "\n"
                f"\tОжидающие анкеты агента: {data.get("agent_pending_month")}\n"
                f"\tПринятые анкеты агента: {data.get("agent_accepted_month")}\n"
                f"\tОтклонённые анкеты агента: {data.get("agent_rejected_month")}\n"
                )
        await message.reply(text)

    @app.on_message(filters.command("stat365") & filters.private & allowed_moder_rule)
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_stat()
        text = ("Общая статистика заявок обновляется раз в час:\n"
                "за послдение 365 дней:\n"
                f"\tОжидающие анкеты оператора: {data.get("operator_pending_year")}\n"
                f"\tПринятые анкеты оператора: {data.get("operator_accepted_year")}\n"
                f"\tОтклонённые анкеты оператора: {data.get("operator_rejected_year")}\n"
                "\n"
                f"\tОжидающие анкеты агента: {data.get("agent_pending_year")}\n"
                f"\tПринятые анкеты агента: {data.get("agent_accepted_year")}\n"
                f"\tОтклонённые анкеты агента: {data.get("agent_rejected_year")}\n"
                )
        await message.reply(text)

    @app.on_message(filters.command("xxl7") & filters.private & allowed_moder_rule)
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_user_stats(message.from_user.username.lower())
        text = ("Личная статистика заявок обновляется раз в час:\n"
                f"\tОжидающие анкеты оператора: {data.get("week", {}).get("operator", {}).get("pending")}\n"
                f"\tПринятые анкеты оператора: {data.get("week", {}).get("operator", {}).get("accepted")}\n"
                f"\tОтклонённые анкеты оператора: {data.get("week", {}).get("operator", {}).get("rejected")}\n"
                "\n"
                f"\tОжидающие анкеты агента: {data.get("week", {}).get("agent", {}).get("pending")}\n"
                f"\tПринятые анкеты агента: {data.get("week", {}).get("agent", {}).get("accepted")}\n"
                f"\tОтклонённые анкеты агента: {data.get("week", {}).get("agent", {}).get("rejected")}\n"
                )
        await message.reply(text)

    @app.on_message(filters.command("xxl30") & filters.private & allowed_moder_rule)
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_user_stats(message.from_user.username.lower())
        text = ("Личная статистика заявок обновляется раз в час:\n"
                f"\tОжидающие анкеты оператора: {data.get("month", {}).get("operator", {}).get("pending")}\n"
                f"\tПринятые анкеты оператора: {data.get("month", {}).get("operator", {}).get("accepted")}\n"
                f"\tОтклонённые анкеты оператора: {data.get("month", {}).get("operator", {}).get("rejected")}\n"
                "\n"
                f"\tОжидающие анкеты агента: {data.get("month", {}).get("agent", {}).get("pending")}\n"
                f"\tПринятые анкеты агента: {data.get("month", {}).get("agent", {}).get("accepted")}\n"
                f"\tОтклонённые анкеты агента: {data.get("month", {}).get("agent", {}).get("rejected")}\n"
                )
        await message.reply(text)

    @app.on_message(filters.command("xxl365") & filters.private & allowed_moder_rule)
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_user_stats(message.from_user.username.lower())
        text = ("Личная статистика заявок обновляется раз в час:\n"
                f"\tОжидающие анкеты оператора: {data.get("year", {}).get("operator", {}).get("pending")}\n"
                f"\tПринятые анкеты оператора: {data.get("year", {}).get("operator", {}).get("accepted")}\n"
                f"\tОтклонённые анкеты оператора: {data.get("year", {}).get("operator", {}).get("rejected")}\n"
                "\n"
                f"\tОжидающие анкеты агента: {data.get("year", {}).get("agent", {}).get("pending")}\n"
                f"\tПринятые анкеты агента: {data.get("year", {}).get("agent", {}).get("accepted")}\n"
                f"\tОтклонённые анкеты агента: {data.get("year", {}).get("agent", {}).get("rejected")}\n"
                )
        await message.reply(text)


    @app.on_message(filters.command("view") & filters.private & allowed_moder_rule)
    async def cmd_view_forms(client: Client, message: Message):
        form = await form_service.get_form(None, "operator", assigned_to=message.from_user.username)

        if not form:
            await message.reply_text("Нет заявок в статусе ожидания.")
            return

        header = (
            f"🆔 Заявка #{form.id} ({"Чётная" if form.id & 1 == 0 else "Не чётная"})\n"
            f"🧑‍💼 Роль: {form.role}\n"
            f"📌 От: @{form.username} (id: {form.user_id})\n"
            f"🕒 Создано: {form.created_at}\n\n"
        )
        content_text = format_content(form.content or {}, form_conv=operator_form_conv if form.role == "operator" else agent_form_conv)
        text = header + "📋 Анкета:\n" + (content_text or "(пусто)")
        text += "\nЧтобы перейти к следующей анкете нажмите -> /view"

        kb = [
            [
                InlineKeyboardButton("✅ Успешно", callback_data=f"form:{form.id}:accept"),
                InlineKeyboardButton("❌ Отклонено", callback_data=f"form:{form.id}:reject"),
            ]
        ]

        try:
            await client.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=InlineKeyboardMarkup(kb),
            )
        except Exception as e:
            await message.reply_text(f"Ошибка при отправке заявки #{form.id}: {e}")

    @app.on_message(filters.private & ~filters.command(ALL_CMDS))
    async def catch_all(client: Client, message: Message):
        # Any non-command message is considered as input to the current FSM
        await operator_form_conv.handle_message(client, message)
        await agent_form_conv.handle_message(client, message)

    @app.on_callback_query()
    async def on_callback(client: Client, callback: CallbackQuery):
        await callback_router(client, callback, session_store, operator_form_conv, form_service, cmd_start)
        await callback_router(client, callback, session_store, agent_form_conv, form_service, cmd_start)
        await callback_global_router(client, callback, form_service, session_store)

    @app.on_message(filters.command("whoami"))
    async def whoami(client: Client, message):
        await message.reply_text(f"CHAT -> id: {message.chat.id} type: {message.chat.type} title: {getattr(message.chat, 'title', None)}")

    logger.info('Starting Pyrogram bot')
    await app.start()
    try:
        await asyncio.Event().wait()
    finally:
        await app.stop()


