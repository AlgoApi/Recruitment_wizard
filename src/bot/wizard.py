import asyncio
import logging
import sqlite3
from pathlib import Path

import uvloop
from pyrogram import Client, filters
from pyrogram.errors import UserNotParticipant
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands, \
    BotCommandScopeChat, BotCommand

from .models.db import init_db
from .utils.busines_text import hello_message
from .utils.utils import format_content, stat_text_gen
from .config import settings, MAX_TRY_RECONNECT
from .logging_config import setup_logging
from .storage.session_store import create_session_store
from .handlers.form_handler import FormConversation
from .services.form_service import FormService
from .handlers.callbacks import callback_router, callback_global_router
from .forms.definition import operator_form, agent_form
from .security.security_rules import allowed_admin_rule, ADMIN_USERNAMES
from .security.security_rules import allowed_moder_rule, MODER_USERNAMES
from .security.security_rules import allowed_superadmin_rule
from .security.security_rules import member_rule
from .security.security_rules import multiple_poller_guardian_fabric as mpg_fabric

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

ALL_CMDS = ["start", "help", "fill", "whoami", "del_admin", "del_moderator", "add_admin", "add_moderator", "stat7",
            "stat30", "stat365", "xxl7", "xxl30", "xxl365", "gay"]

async def is_user_in_chat(app: Client, chat_id: int, user_id: int, username: str) -> bool:
    """
    Проверяет, состоит ли пользователь с данным user_id и username в канале/группе.
    Возвращает True, если пользователь найден и username совпадает.
    """
    try:
        member = await app.get_chat_member(chat_id, user_id)
        # Проверим username (в API он без @)
        if member.user.username and member.user.username.lower() == username.lower():
            return True
        else:
            return False
    except UserNotParticipant:
        # Пользователь не состоит в канале
        return False
    except Exception as e:
        print(f"Ошибка при проверке: {e}")
        return False

def getter_setter_admitted_users_wizard(path: str, username:str,
                      encoding: str = "utf-8", write: bool = False, overwrite: bool = False, data: str = None, _try: bool = False) -> set|None:
    result = dict()
    if write:
        with open(path, "a", encoding=encoding, errors="replace") as f:
            f.write(f"{username}:{data}\n")
        return None
    elif overwrite:
        with open(path, "w", encoding=encoding, errors="replace") as f:
            f.write(f"{data}\n")
        return None
    else:
        try:
            with open(path, "r", encoding=encoding, errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line == "":
                        continue
                    result.update({line.split(":")[0]:line.split(":")[1]})
        except FileNotFoundError:
            if not _try:
                return getter_setter_admitted_users_wizard(path, username, encoding, write, overwrite, data, True)
    return result

async def run_wizard():
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logging.getLogger("redis").setLevel(logging.DEBUG)

    app = None

    await init_db()

    MODER_USERNAMES.update(getter_setter_admitted_users_wizard(path="moders.txt", username=None))
    ADMIN_USERNAMES.update(getter_setter_admitted_users_wizard(path="admins.txt", username=None))

    session_store = await create_session_store()
    form_service = FormService()

    zigma = ""
    attempts = 0

    while Path(f"Recruitment-SO{zigma}D.session").exists():
        if not Path(f"Recruitment-SO{zigma}D.session-journal").exists():
            logger.info(f"attempt use session:{zigma}")
            app = Client(f'Recruitment-SO{zigma}D', bot_token=settings.bot_token, api_id=settings.api_id,
                        api_hash=settings.api_hash)
            break
        else:
            zigma += 'O'

    if not app:
        app = Client(f'Recruitment-SO{zigma}D', bot_token=settings.bot_token, api_id=settings.api_id,
                             api_hash=settings.api_hash)

    operator_form_conv = FormConversation(session_store, form_service, operator_form)
    agent_form_conv = FormConversation(session_store, form_service, agent_form)

    @app.on_message(filters.command(['start', 'help']) & filters.private & member_rule & mpg_fabric(logger, session_store))
    async def cmd_start(client: Client, message: Message):
        text = ""
        commands = [
            BotCommand(command="start", description="Начать")
        ]
        print(ADMIN_USERNAMES)
        print(MODER_USERNAMES)
        if message.from_user.username in list(ADMIN_USERNAMES.values()):
            text += '/add_moderator <username>(без собачки) - Добавить права менеджера пользователю\n'
            text += '/del_moderator <username>(без собачки) - Удалить права менеджера у пользователя\n'
            text += '/del_admin <username>(без собачки) - Удалить права админа у пользователя\n'
            text += '/view - Просмотр пришедших анкет\n'
            commands.append(BotCommand(command="view", description="Просмотр пришедших анкет"))
            text += '/stat[7/30/365] - Просмотр общей статистики за столько-то дней\n'
            text += '/xll[7/30/365] - Просмотр личной статистики за столько-то дней\n'
            text += '/gay - Просмотр текущего закреплённого модератора\n'
            text += '\n'
        if message.from_user.username.lower() == settings.superadmin_username.lower():
            text += '/add_admin <username>(без собачки) - Добавить права админа пользователю\n'
            text += '\n'
        if message.from_user.username in list(MODER_USERNAMES.values()):
            text += '/del_moderator <username>(без собачки) - Удалить права менеджера у пользователя\n'

            text += '\n'

        await app.set_chat_menu_button(
            chat_id=message.from_user.id,
            menu_button=MenuButtonCommands()
        )

        await app.set_bot_commands(commands=commands, scope=BotCommandScopeChat(chat_id=message.from_user.id))

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

    @app.on_message(filters.command(['add_moderator']) & filters.private & allowed_admin_rule & member_rule & mpg_fabric(logger, session_store))
    async def cmd_add_moder(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:]).lower()
            getter_setter_admitted_users_wizard("moders.txt", write=True, data=text_after_command,username=message.from_user.username)
            MODER_USERNAMES.update({message.from_user.username.lower():text_after_command.lower()})
            text = f"Модераторов теперь: {len(MODER_USERNAMES)}\n"
            for nick in list(MODER_USERNAMES.values()):
                text += nick[:3] + "\n"
            await message.reply(text)
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['add_admin']) & filters.private & allowed_superadmin_rule & member_rule & mpg_fabric(logger, session_store))
    async def cmd_add_admin(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            getter_setter_admitted_users_wizard("admins.txt", write=True, data=text_after_command, username=f"{message.from_user.username}{len(ADMIN_USERNAMES)}")
            ADMIN_USERNAMES.update({message.from_user.username:text_after_command})
            text = f"Админов теперь: {len(ADMIN_USERNAMES)}\n"
            for nick in list(ADMIN_USERNAMES.values()):
                text += nick[:3] + "\n"
            await message.reply(text)
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['del_moderator']) & filters.private & (allowed_moder_rule | allowed_admin_rule) & member_rule & mpg_fabric(logger, session_store))
    async def cmd_del_moder(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            print(MODER_USERNAMES)
            print(text_after_command)
            if text_after_command in list(MODER_USERNAMES.values()):
                if MODER_USERNAMES.get(message.from_user.username, "") == text_after_command:
                    for id_name, nick in list(MODER_USERNAMES.items()):
                        if message.from_user.username == id_name:
                            del MODER_USERNAMES[f"{id_name}"]
                    text = f"Модераторов теперь: {len(MODER_USERNAMES)}\n"
                    for nick in list(MODER_USERNAMES.values()):
                        text += nick[:3] + "...\n"
                    await message.reply(text)
                    print(MODER_USERNAMES)
                    getter_setter_admitted_users_wizard("moders.txt", overwrite=True, data="\n".join(f"{k}:{v}" for k, v in MODER_USERNAMES.items()), username=message.from_user.username)
                else:
                    await message.reply("Ты можешь отправить в отставку только своих")
            else:
                await message.reply("Уже в отставке")
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['del_admin']) & filters.private & allowed_superadmin_rule & member_rule & mpg_fabric(logger, session_store))
    async def cmd_del_admin(client: Client, message: Message):
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            if text_after_command in list(ADMIN_USERNAMES.values()):
                if ADMIN_USERNAMES.get(message.from_user.username, "") == text_after_command or message.from_user.username.lower() == settings.superadmin_username.lower():
                    print(ADMIN_USERNAMES)
                    for id_name, nick in list(ADMIN_USERNAMES.items()):
                        if text_after_command == nick:
                            del ADMIN_USERNAMES[f"{id_name}"]
                    print("----")
                    print(ADMIN_USERNAMES)
                    text = f"Админов теперь: {len(ADMIN_USERNAMES)}\n"
                    for nick in list(ADMIN_USERNAMES.values()):
                        text += nick[:3] + "...\n"
                    await message.reply(text)
                    getter_setter_admitted_users_wizard("admins.txt", overwrite=True, data="\n".join(f"{k}:{v}" for k, v in ADMIN_USERNAMES.items()), username=message.from_user.username)
                else:
                    await message.reply("Ты можешь отправить в отставку только себя")
            else:
                await message.reply("Уже в отставке")
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command("stat7") & filters.private & allowed_admin_rule & member_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_forms_stats(period="7 days")
        text = "Общая статистика заявок за послдение 7 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("stat30") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_forms_stats(period="29 days")
        text = "Общая статистика заявок за послдение 30 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("stat365") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_forms_stats(period="364 days")
        text = "Общая статистика заявок за послдение 365 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("xxl7") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_forms_stats(period="6 days", assigned_to=message.from_user.username.lower())
        text = "Личная статистика заявок за последние 7 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("xxl30") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_forms_stats(period="29 days", assigned_to=message.from_user.username.lower())
        text = "Личная статистика заявок за последние 30 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("xxl365") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        data = await form_service.get_forms_stats(period="364 days", assigned_to=message.from_user.username.lower())
        text = "Личная статистика заявок за последние 365 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)


    @app.on_message(filters.command("view") & filters.private & allowed_admin_rule & member_rule & mpg_fabric(logger, session_store))
    async def cmd_view_forms(client: Client, message: Message):
        form = await form_service.get_form(None, "operator", assigned_to=MODER_USERNAMES.get(message.from_user.username.lower(), "Undefined"))

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
                protect_content=True
            )
        except Exception as e:
            await message.reply_text(f"Ошибка при отправке заявки #{form.id}: {e}")

    @app.on_message(filters.command('mymoder') & mpg_fabric(logger, session_store) & allowed_admin_rule & filters.private)
    async def opers(client: Client, message):
        await message.reply_text(f"{MODER_USERNAMES.get(message.from_user.username)}")

    @app.on_message(filters.command('gay') & mpg_fabric(logger, session_store) & allowed_admin_rule)
    async def pashalko(client: Client, message):
        await client.send_photo(message.from_user.id, caption=f"{MODER_USERNAMES.get(message.from_user.username)}", photo="AgACAgIAAxkBAAIDM2kM9OrTy8y7zLWKDMEiVt2B5rbQAAJxD2sbOlNoSFGjptx13Ps1AAgBAAMCAAN5AAceBA")

    @app.on_message(filters.private & ~filters.command(ALL_CMDS) & member_rule & mpg_fabric(logger, session_store))
    async def catch_all(client: Client, message: Message):
        # Any non-command message is considered as input to the current FSM
        await operator_form_conv.handle_message(client, message)
        await agent_form_conv.handle_message(client, message)

    @app.on_callback_query(member_rule & mpg_fabric(logger, session_store))
    async def on_callback(client: Client, callback: CallbackQuery):
        next_pass = await callback_router(client, callback, session_store, operator_form_conv, form_service, cmd_start)
        if next_pass or next_pass is None:
            await callback_router(client, callback, session_store, agent_form_conv, form_service, cmd_start)
        await callback_global_router(client, callback, form_service, session_store)
        chat_id = callback.message.chat.id
        msg_id = callback.message.id
        key = f"processed:msg:{chat_id}:{msg_id}"
        await session_store.del_other(key)
        logger.info("Cleared callback for processing %s:%s", chat_id, msg_id)

    @app.on_message(filters.command("whoami") & mpg_fabric(logger, session_store))
    async def whoami(client: Client, message):
        await message.reply_text(f"CHAT -> id: {message.chat.id} type: {message.chat.type} title: {getattr(message.chat, 'title', None)}, reply_to_message_id: {message.reply_to_message_id}")
        try:
            await message.reply_text(f"video_id: {message.video.file_id}")
        except AttributeError:
            pass
        try:
            await message.reply_text(f"photo_id: {message.photo.file_id}")
        except AttributeError:
            pass
        try:
            await message.reply_text(f"gif_id: {message.animation.file_id}")
        except AttributeError:
            pass



    logger.info('Starting Pyrogram bot')
    await app.start()
    try:
        await asyncio.Event().wait()
    finally:
        await app.stop()


