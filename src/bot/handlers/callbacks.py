import asyncio

import random
from typing import Sequence

from pyrogram import Client
from pyrogram.errors import MessageIdInvalid, QueryIdInvalid, FloodWait, Forbidden

from pyrogram.raw.functions.messages import SendMessage as SendMessage_Raw
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from .form_handler import FormConversation
from ..config import settings
from ..security.security_rules import MODER_USERNAMES
from ..services.form_service import FormService

from ..storage.session_store import RedisSessionStore
from ..utils.busines_text import *
from ..utils.utils import format_content, translate_role, make_raw_reply_markup

logger = logging.getLogger(__name__)

async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except QueryIdInvalid:
        pass
    return



async def send_text_to_topic(client: Client, chat_id: int, topic_init_msg_id: int, text: str, kb: Sequence[Sequence[InlineKeyboardButton]] | None = None):
    logger.info(f"{chat_id} send_text_to_topic")
    peer = await client.resolve_peer(chat_id)
    random_id = random.getrandbits(32)
    logger.debug(f"{chat_id} send_text_to_topic peer:{"True" if peer else "False"} random_id:{random_id}")

    raw_reply = None
    if kb:
        raw_reply = await make_raw_reply_markup(kb)

    await client.invoke(
        SendMessage_Raw(
            peer=peer,
            message=text,
            random_id=random_id,
            reply_to_msg_id=topic_init_msg_id,
            reply_markup=raw_reply
        )
    )
    return True

async def safe_send_to_user(client:Client, user_identifier, text_vv, reply_markup_v:InlineKeyboardMarkup=None):
        try:
            await client.send_message(chat_id=user_identifier, text=text_vv, reply_markup=reply_markup_v)
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю: {e}")
            return False

async def valid_start_role(client:Client, form_service: FormService, callback: CallbackQuery, session:dict, sesssion_store:RedisSessionStore, user_id, role, data):
    logger.info(f"{callback.from_user.username or callback.from_user.id} validation form start command")
    parts = data.split(':')
    command = parts[1]
    if await form_service.is_submited(user_id, role):
        logger.info(f"{callback.from_user.username or callback.from_user.id} waiting")
        new_message = await callback.message.reply_text(wait_text.replace("{ROLE_NOT_ASSIGNED}", translate_role(role)))
        if session.get('menu_id'):
            try:
                await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
            except MessageIdInvalid:
                pass
        session['menu_id'] = new_message.id
        await sesssion_store.set_overwrite(user_id, session)
        await safe_answer(callback)
        return ""
    expiry = await form_service.is_cooldown(user_id, role)
    if expiry > 0:
        logger.info(f"{callback.from_user.username or callback.from_user.id} cooldown")
        new_message = await callback.message.reply_text(cooldown_text + f"{expiry} минут")
        if session.get('menu_id'):
            try:
                await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
            except MessageIdInvalid:
                pass
        session['menu_id'] = new_message.id
        await sesssion_store.set_overwrite(user_id, session)
        await safe_answer(callback)
        return ""

    return command

async def callback_router(client: Client, callback: CallbackQuery, sesssion_store: RedisSessionStore, form_conv: FormConversation, form_service: FormService, cmd_start: callable):
    data = callback.data or ''
    if data.startswith("info"):
        return None
    user = callback.from_user
    logger.info(f"{user.username or user.id} {user.first_name} callback router received callback:{data}")
    session = await sesssion_store.get(user.id) or {}
    session_role = session.get("definition_id", None)
    parts = data.split(':')

    form_not_match = False

    if data.startswith('operator:') and form_conv.form_def.id == "operator":
        command = await valid_start_role(client, form_service, callback, session, sesssion_store, user.id, "operator",
                                         data)
        if command == "start":
            logger.info(f"{user.username or user.id} {user.first_name} callback router accept callback - start operator")
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return None
    elif data.startswith('agent:') and form_conv.form_def.id == "agent":
        command = await valid_start_role(client, form_service, callback, session, sesssion_store, user.id, "agent", data)
        if command == "start":
            logger.info(f"{user.username or user.id} {user.first_name} callback router accept callback - start agent")
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return None

    else:
        if data.startswith('agent:') or data.startswith('operator:'):
            logger.debug(f"{user.username or user.id} {user.first_name} form_not_match TRUE")
            form_not_match = True

    if data == "cmd_start":
        logger.info(f"{user.username or user.id} {user.first_name} callback router accept callback - cmd_start")
        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
            except MessageIdInvalid:
                pass
            except AttributeError:
                try:
                    await client.delete_messages(callback.message.sender_chat.id, session.get('menu_id', None))
                except Exception:
                    try:
                        await client.delete_messages(callback.message.from_user.id, session.get('menu_id', None))
                    except Exception:
                        pass
        if session.get('run', False):
            logger.debug(f"session 'run' is True")
            try:
                await cmd_start()
            except Exception as e:
                logger.warning(e)
        else:
            logger.debug(f"session 'run' is False")
        await safe_answer(callback)
        return False
    if data == "cmd_start_exec":
        logger.info(f"{user.username or user.id} {user.first_name} callback router accept callback - cmd_start_exec")
        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
            except MessageIdInvalid:
                pass
        await cmd_start(client, callback.message)
        await safe_answer(callback)
        return False

    elif data.startswith("send_questions:") and form_conv.form_def.id == parts[1]:
        logger.info(f"{user.username or user.id} {user.first_name} callback router accept callback - send_questions")
        await form_conv._send_page(client, callback.message.chat.id, user.id)
        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
            except MessageIdInvalid:
                pass
        await safe_answer(callback)
        return None

    elif session_role and session_role != form_conv.form_def.id:
        logger.info(f"{user.username or user.id} {user.first_name} callback router reject callback - {session_role} != {form_conv.form_def.id}")

        await safe_answer(callback)
        return None

    elif data.startswith('trouble:'):
        logger.info(f"{user.username or user.id} {user.first_name} callback router accept callback - trouble")
        _, raw_id = data.split(":")
        form_id = int(raw_id)

        logger.debug(f"{user.username or user.id} {user.first_name} callback router trouble try get form")
        form = await form_service.get_form(form_id=form_id, status=True)

        if form.role == form_conv.form_def.id:
            logger.info(f"{user.username or user.id} {user.first_name} callback router trouble get form {form.username or form.user_id}")
            header = (
                "**❗НЕ МОЖЕТ НАПИСАТЬ❗**\n"
                f"🆔 Заявка #{form.id} ({"Чётная" if form.id & 1 == 0 else "Не чётная"}) ({form.assigned_to})\n"
                f"🧑‍💼 Роль: {form.role}\n"
                f"📌 От: @{form.username} (id: {form.user_id})\n"
                f"🕒 Создано: {form.created_at}\n\n"
            )
            content_text = format_content(form.content or {}, form_conv=form_conv)
            text = header + "📋 Анкета:\n" + (content_text or "(пусто)")

            if form.role == "operator":
                logger.info(f"{user.username or user.id} {user.first_name} callback router trouble send for operator")
                await client.send_message(chat_id=form.assigned_to, text=text)
            elif form.role == "agent":
                logger.info(f"{user.username or user.id} {user.first_name} callback router trouble send for agent")
                try:
                    await send_text_to_topic(client, chat_id=settings.group_id, topic_init_msg_id=settings.agent_group_id, text=text)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await send_text_to_topic(client, chat_id=settings.group_id, topic_init_msg_id=settings.agent_group_id, text=text)
                except Forbidden:
                    logger.error("Бот не имеет прав писать в эту группу или был исключён.")
                except Exception as e:
                    logger.error("Ошибка при отправке:", e)
            await callback.message.reply_text(trouble)
        await safe_answer(callback)
        return None

    elif session:
        if data.startswith('fill:page:'):
            page = int(parts[2])
            form_name = parts[3]
            if form_name == form_conv.form_def.id:
                logger.info(f"{user.username or user.id} {user.first_name} callback router accept callback - start fill page {page} : {form_name}")
                session["run"] = True
                pages = list(form_conv.form_def.pages())
                session["question"] = 0
                for question in pages[session['page']]:
                    all_answeres = list(session["answers"].keys())
                    for key in all_answeres:
                        if question.key == key:
                            session["question"] += 1
                session['page'] = page

                if session.get('menu_id', None):
                    try:
                        await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
                    except MessageIdInvalid:
                        pass

                if len(pages[page]) <= session["question"]:
                    logger.warning(f"{user.username or user.id} {user.first_name} callback router start fill page - clear all answers")
                    # await callback.message.reply("На этой странице всё, переходите к следующей")
                    for question in pages[page]:
                        all_answeres = list(session["answers"].keys())
                        for key in all_answeres:
                            if question.key == key:
                                session["answers"].pop(key)
                                session["question"] -= 1
                await form_conv._send_page(client, callback.message.chat.id, user.id)
                new_message = await callback.message.reply(f'Отправьте {pages[page][session["question"]].label}')
                session['menu_id'] = new_message.id
                await sesssion_store.set_overwrite(user.id, session)
            else :
                logger.info(f"{user.username or user.id} {user.first_name} callback router reject callback - fill page, because {form_name} != {form_conv.form_def.id}")
            await safe_answer(callback)
            return None
        elif data.startswith('nav:'):
            action = parts[1]
            form_name = parts[2]
            if form_name == form_conv.form_def.id:
                logger.info(f"{user.username or user.id} {user.first_name} callback router accept nav {action} {form_name}")
                if action == 'next':
                    logger.info(f"{user.username or user.id} {user.first_name} callback router nav action next")
                    session['page'] = session.get('page', 0) + 1
                    pages = list(form_conv.form_def.pages())
                    session["question"] = 0
                    if session['page']+1 > len(pages):
                        session['page'] = 0
                    for question in pages[session['page']]:
                        all_answeres = list(session["answers"].keys())
                        for key in all_answeres:
                            if question.key == key:
                                session["question"] += 1
                else:
                    logger.info(f"{user.username or user.id} {user.first_name} callback router nav action prev")
                    if (session.get('page', 0) - 1) < 0:
                        if session.get('menu_id', None):
                            try:
                                await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
                            except MessageIdInvalid:
                                pass
                            await form_conv.start(client, callback)
                            await callback.answer()
                            return None
                    session['page'] = session.get('page', 0) - 1
                    pages = list(form_conv.form_def.pages())
                    session["question"] = 0
                    for question in pages[session['page']]:
                        all_answeres = list(session["answers"].keys())
                        for key in all_answeres:
                            if question.key == key:
                                session["question"] += 1
                logger.debug(f"{user.username or user.id} {user.first_name} callback router nav, now session['run'] = False")
                session["run"] = False
                await sesssion_store.set_overwrite(user.id, session)
                await form_conv._send_page(client, callback.message.chat.id or user.id, user.id)
            else:
                logger.info(f"{user.username or user.id} {user.first_name} callback router reject callback - nav, because {form_name} != {form_conv.form_def.id}")

            await callback.answer()
            return None
        elif data == 'submit:confirm':
            logger.info(f"{user.username or user.id} {user.first_name} callback router accept submit:confirm")
            form = await form_service.create_draft(user.id, (user.username or user.first_name), session.get('definition_id', "UNDEFINED"), session.get('answers', {}))
            await form_service.submit_form(form)
            session = await sesssion_store.pop(user.id)
            if session.get('menu_id', None):
                try:
                    await client.delete_messages(callback.message.chat.id, session.get('menu_id', None))
                except MessageIdInvalid:
                    pass
            role_txt = translate_role(session.get("definition_id", ""))

            new_message = await callback.message.reply(anketa_sent.replace("{ROLE_NOT_ASSIGNED}", role_txt))
            session['menu_id'] = new_message.id
            await sesssion_store.set_overwrite(user.id, session)
            #await cmd_start(client, callback.message)
            topic_init_msg_id = 1
            if session.get('definition_id', "UNDEFINED") == 'agent':
                topic_init_msg_id = settings.agent_group_id
                logger.info(f"{user.username or user.id} {user.first_name} callback router submit:confirm interpreted agent")
            if session.get('definition_id', "UNDEFINED") == 'operator':
                topic_init_msg_id = settings.operator_group_id
                logger.info(f"{user.username or user.id} {user.first_name} callback router submit:confirm interpreted operator")
            header = (
                f"🆔 Заявка #{form.id} ({"Чётная" if form.id & 1 == 0 else "Не чётная"}) (нет решения)\n"
                f"🧑‍💼 Роль: {form.role}\n"
                f"📌 От: @{form.username or user.first_name} (id: {form.user_id})\n"
                f"🕒 Создано: {form.created_at}\n\n"
            )
            content_text = format_content(form.content or {}, form_conv=form_conv)
            text = header + "📋 Анкета:\n" + (content_text or "(пусто)")

            kb = [
                [
                    InlineKeyboardButton("✅ Успешно", callback_data=f"form:{form.id}:accept"),
                    InlineKeyboardButton("❌ Отклонено", callback_data=f"form:{form.id}:reject"),
                ]
            ]

            try:
                await send_text_to_topic(client=client, chat_id=settings.group_id,
                                         topic_init_msg_id=topic_init_msg_id, text=text, kb=kb)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await send_text_to_topic(client=client, chat_id=settings.group_id,
                                         topic_init_msg_id=topic_init_msg_id, text=text, kb=kb)
            except Forbidden:
                logger.error("Бот не имеет прав писать в эту группу или был исключён.")
            except Exception as e:
                logger.error("Ошибка при отправке:", e)

            await safe_answer(callback)
            return None
        else:
            if not form_not_match:
                logger.info(f"{user.username or user.id} {user.first_name} callback router reject callback form_not_match")
                await callback.message.reply("Нажми /start <-")
                await safe_answer(callback)
                return None
            return None
    elif data == 'submit:cancel':
        await callback.message.reply('Отправка отменена.')
        await callback.answer()
        return None
    else:
        #await callback.message.reply('Нажми /start <- тык')
        await callback.answer()
        return None
