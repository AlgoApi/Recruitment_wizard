from .services.staff_service import StaffService

print("Welcome to AlgoApi Wizard")
import asyncio
import logging
from pathlib import Path

import uvloop
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands, \
    BotCommandScopeChat, BotCommand

from .models.db import AsyncSessionLocal
from .utils.busines_text import hello_message
from .utils.utils import format_content, stat_text_gen
from .config import settings
from .logging_config import setup_logging
from .storage.session_store import create_session_store
from .handlers.form_handler import FormConversation
from .services.form_service import FormService
from .services.user_service import UserService
from .handlers.callbacks import callback_router
from .handlers.global_callbacks import callback_global_router
from .forms.definition import operator_form, agent_form
from .security.security_rules import allowed_admin_rule, ADMIN_USERNAMES, cheker_channel_member
from .security.security_rules import allowed_moder_rule, MODER_USERNAMES
from .security.security_rules import allowed_superadmin_rule
from .security.security_rules import multiple_poller_guardian_fabric as mpg_fabric

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

ALL_CMDS = ["start", "help", "fill", "whoami", "del_admin", "del_moderator", "add_admin", "add_moderator", "stat7",
            "stat30", "stat365", "xxl7", "xxl30", "xxl365", "gay"]

async def run_wizard():
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logging.getLogger("redis").setLevel(logging.DEBUG)

    app = None

    logger.info(f"init_db")
    await AsyncSessionLocal.init_db()

    logger.info("session_store")
    session_store = await create_session_store()
    logger.info("staff_service")
    staff_service = StaffService(AsyncSessionLocal)
    logger.info("form_service")
    form_service = FormService(AsyncSessionLocal)
    logger.info("user_service")
    user_service = UserService(AsyncSessionLocal)

    logger.info("get moder db")
    moders_rows = await staff_service.get_staff(role="moderator", limit=False)
    MODER_USERNAMES.update({row.assigned_to: row.username for row in moders_rows})
    logger.info(MODER_USERNAMES)
    del moders_rows
    logger.info("get admins db")
    admins_rows = await staff_service.get_staff(role="admin", limit=False)
    ADMIN_USERNAMES.update({row.assigned_to: row.username for row in admins_rows})
    logger.info(ADMIN_USERNAMES)
    del admins_rows

    zigma = ""
    attempts = 0

    while Path(f"Recruitment-SO{zigma}D.session").exists():
        logger.info(f"session found '{zigma}'")
        if len(zigma) > 1:
            logger.error(f"session found '{zigma}' -> length > 1")
        if not Path(f"Recruitment-SO{zigma}D.lock").exists():
            logger.info(f"attempt use session:{zigma}")
            open(f"Recruitment-SO{zigma}D.lock", "a").close()
            app = Client(f'Recruitment-SO{zigma}D', bot_token=settings.bot_token, api_id=settings.api_id,
                        api_hash=settings.api_hash)
            break
        else:
            logger.info(f"session '{zigma}' locked")
            zigma += 'O'

    if not app:
        logger.warning(f"app is None")
        app = Client(f'Recruitment-SO{zigma}D', bot_token=settings.bot_token, api_id=settings.api_id,
                             api_hash=settings.api_hash)

    logger.info("init operator_form_conv")
    operator_form_conv = FormConversation(session_store, form_service, operator_form)
    logger.info("init agent_form_conv")
    agent_form_conv = FormConversation(session_store, form_service, agent_form)

    @app.on_message(filters.command(['start', 'help']) & filters.private & mpg_fabric(logger, session_store))
    async def cmd_start(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used start")
        await cheker_channel_member(client, message, settings.channel_id, True)
        text = ""
        commands = [
            BotCommand(command="start", description="Начать")
        ]
        if (message.from_user.username or "").lower() in list(ADMIN_USERNAMES.values()):
            text += '/add_moderator <username>(без собачки) - Добавить права менеджера пользователю\n'
            text += '/del_moderator <username>(без собачки) - Удалить права менеджера у пользователя\n'
            text += '/del_admin <username>(без собачки) - Удалить права админа у пользователя\n'
            text += '/view - Просмотр пришедших анкет\n'
            commands.append(BotCommand(command="view", description="Просмотр пришедших анкет"))
            text += '/stat[7/30/365] - Просмотр общей статистики за столько-то дней\n'
            text += '/xll[7/30/365] - Просмотр личной статистики за столько-то дней\n'
            text += '/gay - Просмотр текущего закреплённого модератора\n'
            text += '/setspam - начать рассылку всем\n'
            text += '\n Что делать если есть какие-то цифры и не рабочий @username:\n      tg://<тот самый не рабочий username без @>?id=<те самые цифры>\n      пример: tg://Виолета?id=812345678\n'
        if (message.from_user.username or "").lower() == settings.superadmin_username.lower():
            text += '/add_admin <username>(без собачки) - Добавить права админа пользователю\n'
            text += '\n'
        if (message.from_user.username or "").lower() in list(MODER_USERNAMES.values()):
            text += '/del_moderator <username>(без собачки) - Удалить права менеджера у пользователя\n'
            text += '\n'

        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} start set_chat_menu_button")
        await app.set_chat_menu_button(
            chat_id=message.from_user.id,
            menu_button=MenuButtonCommands()
        )

        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} start set_bot_commands")
        await app.set_bot_commands(commands=commands, scope=BotCommandScopeChat(chat_id=message.from_user.id))

        text += hello_message

        kb = [
            [
                InlineKeyboardButton("Оператор", callback_data=f"operator:start"),
                InlineKeyboardButton("Агент", callback_data=f"agent:start"),
                InlineKeyboardButton("Информация", callback_data=f"info:info"),
            ]
        ]

        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} start reply")
        await message.reply(text, reply_markup=InlineKeyboardMarkup(kb))

        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} try to add in 'users' table")
        user = await user_service.create_draft(message.from_user.id, (message.from_user.username or message.from_user.first_name))
        await user_service.submit_user(user)


    '''
    DEPRECATED
    @app.on_message(filters.command(['fill']) & filters.private)
    async def cmd_fill(client: Client, message: Message):
        await operator_form_conv.start(client, message)
    '''

    @app.on_message(filters.command(['add_moderator']) & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_add_moder(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used add_moderator")
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:]).lower()
            await staff_service.update_form(find_role="moderator", find_assigned_to=message.from_user.username.lower(), actual=False)
            staff = await staff_service.create_draft(text_after_command, "moderator", message.from_user.username.lower(), True)
            await staff_service.submit_staff(staff)
            MODER_USERNAMES.update({message.from_user.username.lower():text_after_command.lower()})
            text = f"Модераторов теперь: {len(MODER_USERNAMES)}\n"
            for nick in list(MODER_USERNAMES.values()):
                text += nick[:3] + "\n"
            await message.reply(text)
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['add_admin']) & filters.private & allowed_superadmin_rule & mpg_fabric(logger, session_store))
    async def cmd_add_admin(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used add_admin")
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            len_adm = len(ADMIN_USERNAMES)
            ADMIN_USERNAMES.update({f"{message.from_user.username.lower()}{len_adm}":text_after_command})
            # await staff_service.update_form(find_role="admin", find_assigned_to="alogapi", actual=False)
            staff = await staff_service.create_draft(text_after_command, "admin", f"{message.from_user.username.lower()}{len_adm}", True)
            await staff_service.submit_staff(staff)
            text = f"Админов теперь: {len(ADMIN_USERNAMES)}\n"
            for nick in list(ADMIN_USERNAMES.values()):
                text += nick[:3] + "\n"
            await message.reply(text)
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['del_moderator']) & filters.private & (allowed_moder_rule | allowed_admin_rule) & mpg_fabric(logger, session_store))
    async def cmd_del_moder(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used del_moderator")
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            if text_after_command in list(MODER_USERNAMES.values()):
                if MODER_USERNAMES.get(message.from_user.username, "") == text_after_command:
                    for id_name, nick in list(MODER_USERNAMES.items()):
                        if message.from_user.username == id_name:
                            del MODER_USERNAMES[f"{id_name}"]
                    text = f"Модераторов теперь: {len(MODER_USERNAMES)}\n"
                    await staff_service.update_form(text_after_command, "moderator", message.from_user.username.lower(), actual=False)
                    for nick in list(MODER_USERNAMES.values()):
                        text += nick[:3] + "...\n"
                    await message.reply(text)
                else:
                    await message.reply("Ты можешь отправить в отставку только своих")
            else:
                await message.reply("Уже в отставке")
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command(['del_admin']) & filters.private & allowed_superadmin_rule & mpg_fabric(logger, session_store))
    async def cmd_del_admin(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used del_admin")
        args = message.command
        if len(args) > 1:
            text_after_command = " ".join(args[1:])
            text_after_command = text_after_command.lower()
            if text_after_command in list(ADMIN_USERNAMES.values()):
                if ADMIN_USERNAMES.get(message.from_user.username.lower(), "") == text_after_command or message.from_user.username.lower() == settings.superadmin_username.lower():
                    for id_name, nick in list(ADMIN_USERNAMES.items()):
                        if text_after_command == nick:
                            del ADMIN_USERNAMES[f"{id_name}"]
                    await staff_service.update_form(text_after_command, "admin", message.from_user.username.lower(), actual=False)
                    text = f"Админов теперь: {len(ADMIN_USERNAMES)}\n"
                    for nick in list(ADMIN_USERNAMES.values()):
                        text += nick[:3] + "...\n"
                    await message.reply(text)
                else:
                    await message.reply("Ты можешь отправить в отставку только себя")
            else:
                await message.reply("Уже в отставке")
        else:
            await message.reply("В следующий раз напиши username после команды")

    @app.on_message(filters.command("stat7") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used stat7")
        data = await form_service.get_forms_stats(period="7 days")
        text = "Общая статистика заявок за послдение 7 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("stat30") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used stat30")
        data = await form_service.get_forms_stats(period="29 days")
        text = "Общая статистика заявок за послдение 30 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("stat365") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used stat365")
        data = await form_service.get_forms_stats(period="364 days")
        text = "Общая статистика заявок за послдение 365 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("xxl7") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used xxl7")
        data = await form_service.get_forms_stats(period="6 days", assigned_to=message.from_user.username.lower())
        text = "Личная статистика заявок за последние 7 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("xxl30") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used xxl30")
        data = await form_service.get_forms_stats(period="29 days", assigned_to=message.from_user.username.lower())
        text = "Личная статистика заявок за последние 30 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("xxl365") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_stat(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used xxl365")
        data = await form_service.get_forms_stats(period="364 days", assigned_to=message.from_user.username.lower())
        text = "Личная статистика заявок за последние 365 дней:\n"
        text += stat_text_gen(data)
        await message.reply(text)

    @app.on_message(filters.command("setspam") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def spam_set(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used setspam")
        await message.reply("Следующее Ваше сообщение будет сохранено в качестве рассылки, также можно добавить url кнопки: для этого первой строкой перечислите каждая на отдельной строке: [текст кнопки](url ссылка) включая скобки, максимум 4 шт\nПосле того как будете уверены в отправки этого сообщения - /startspam <- тык \nили если хотите отменить не пишите /startspam \nили отредактируйте это сообщение, удостоверьтесь и /startspam")

    @app.on_message(filters.command("startspam") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def spam_start(client: Client, message: Message):
        accepted_rassilok = 0
        rejected_rassilok = 0
        copy_message_id = message.id - 1
        await message.reply("Рассылка началась")

        msg = await client.get_messages(message.chat.id, copy_message_id)
        if msg and msg.from_user.is_bot:
            copy_message_id -= 1
            msg = await client.get_messages(message.chat.id, copy_message_id)
        if not msg or msg.from_user.is_bot or msg.text.startswith("/setspam"):
            await message.reply(f"Рассылка окончена.\nпроверьте наличие Вашего сообщения")
            return
        users = await user_service.get_user(limit=False)
        for user_entry in users:
            try:
                msg = await client.copy_message(chat_id=user_entry.user_id, message_id=copy_message_id,
                                                from_chat_id=message.chat.id)
                if msg is not None:
                    accepted_rassilok += 1
                else:
                    rejected_rassilok += 1
            except Exception:
                logger.warning(f"Failed to send rassilka to {user_entry.user_id}")
                rejected_rassilok += 1
        await message.reply(f"Рассылка окончена.\nотправлено: {accepted_rassilok}, отклонено: {rejected_rassilok}")

    @app.on_message(filters.command("spam2") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def spam_tool(client: Client, message: Message):
        await session_store.del_other(f"{message.chat.id}:spam")
        kb = [[InlineKeyboardButton(text="Рассылка с кнопками url (с ссылкой)", callback_data="spam:url:")],
              [InlineKeyboardButton(text="Рассылка без кнопок", callback_data="spam:content")],
              [InlineKeyboardButton(text="Рассылка с кнопками callback (обратитесь к админу за подробностями)", callback_data="spam:callback:")]]
        await message.reply(f"Выбери вариант рассылки:", reply_markup=InlineKeyboardMarkup(kb))

    @app.on_message(filters.command("clear_spam2") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def spam_tool(client: Client, message: Message):
        await session_store.del_other(f"{message.chat.id}:spam")
        await message.reply("Готово")

    @app.on_message(filters.command("view") & filters.private & allowed_admin_rule & mpg_fabric(logger, session_store))
    async def cmd_view_forms(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used view")
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
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} used mymoder")
        await message.reply_text(f"{MODER_USERNAMES.get(message.from_user.username)}")

    @app.on_message(filters.command('gen_callback') & mpg_fabric(logger, session_store) & allowed_admin_rule)
    async def debug_callback(client: Client, message):
        parts = message.text.split()
        if len(parts) < 2:
            return await message.reply_text("Usage: /gen_callback <callback>")

        callback_v = parts[1]

        await message.reply_text(f"DEBUG CALLBACK BUTTON: {callback_v}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("DELETE AFTER CLICK", callback_data=callback_v)]]))

    @app.on_message(filters.command('gay') & mpg_fabric(logger, session_store) & allowed_admin_rule)
    async def pashalko(client: Client, message: Message):
        parts = message.text.split()
        if len(parts) < 2:
            return await message.reply_text("Usage: /pashalko <chat_id>")

        raw = parts[1]
        try:
            chat_id_p = int(raw)
        except ValueError:
            return await message.reply_text("chat_id должен быть числом")

        logger.info(f"requested chat_id = {chat_id_p}")
        # проверка get_chat
        try:
            chat = await app.get_chat(chat_id_p)
            logger.info(
                f"get_chat resolved: id={chat.id} type={getattr(chat, 'type', None)} title={getattr(chat, 'title', None)}")
        except Exception as e:
            logger.exception("get_chat failed")
            await message.reply_text(f"get_chat error: {e}")
            return None

        # запросим первые 1..99
        ids = list(range(1, 100))
        msgs = await app.get_messages(chat_id=chat_id_p, message_ids=ids)
        for idx, m in zip(ids, msgs):
            if m is None:
                logger.info(f"[{idx}] None")
                continue
            calc_chat_id = getattr(m.chat, "id", None) or "none"
            frm = getattr(m.from_user, "id", None)
            logger.info(
                f"[{idx}] msg.chat.id = {calc_chat_id} msg.message_id = {m.id} from = {frm} text={m.text or m.caption}")
        logger.info(f"end chat history for {chat_id_p}")
        return None

    @app.on_message(filters.private & ~filters.command(ALL_CMDS) & mpg_fabric(logger, session_store))
    async def catch_all(client: Client, message: Message):
        logger.info(f"{message.from_user.username or message.from_user.id} {message.from_user.first_name} not command, catch message")
        # Any non-command message is considered as input to the current FSM
        await operator_form_conv.handle_message(client, message)
        await agent_form_conv.handle_message(client, message)

    @app.on_callback_query(mpg_fabric(logger, session_store, False))
    async def on_callback(client: Client, callback: CallbackQuery):
        logger.info(f"{callback.from_user.username or callback.from_user.id} {callback.from_user.first_name} get calllback")
        try:
            chat_id = callback.from_user.id
        except AttributeError:
            try:
                chat_id = callback.message.chat.id
            except AttributeError:
                chat_id = callback.message.from_user.id

        msg_id = callback.message.id

        key = f"processed:msg:{chat_id}:{msg_id}:{callback.data}"
        ttl_seconds = 60 * 30
        got = await session_store.set_other(key, "1", nx=True, ex=ttl_seconds)
        if not got:
            logger.info("SSSkipping already-processed message %s:%s", chat_id, msg_id)
            return False
        logger.info(
            f"{callback.from_user.username or callback.from_user.id} {callback.from_user.first_name} callback_global_router get calllback")
        global_call = await callback_global_router(client, callback, form_service, session_store, user_service, staff_service)
        if not global_call:
            next_pass = await callback_router(client, callback, session_store, operator_form_conv, form_service, cmd_start)
            if next_pass or next_pass is None:
                logger.info(f"{callback.from_user.username or callback.from_user.id} {callback.from_user.first_name} operator_form_conv accept calllback")
                logger.info(f"{callback.from_user.username or callback.from_user.id} {callback.from_user.first_name} agent_form_conv get calllback")
                await callback_router(client, callback, session_store, agent_form_conv, form_service, cmd_start)
            else:
                logger.warning(f"{callback.from_user.username or callback.from_user.id} {callback.from_user.first_name} operator_form_conv NOT accept calllback")

        return None

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



    logger.info('Summoning the ARCHMAGE of AlgoApi Recruitment')
    await app.start()
    try:
        await asyncio.Event().wait()
    finally:
        await app.stop()
    print("AVADA KEDAVRA")
    logger.info("AVADA KEDAVRA")
