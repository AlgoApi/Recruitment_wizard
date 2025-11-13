import asyncio
import logging
import random
from typing import Sequence

from pyrogram import Client
from pyrogram.errors import MessageIdInvalid, QueryIdInvalid, FloodWait, Forbidden
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.raw.functions.messages import SendMessage as SendMessage_Raw
from pyrogram.raw import functions, types as raw_types

from .form_handler import FormConversation
from ..security.security_rules import MODER_USERNAMES
from ..storage.session_store import RedisSessionStore
from ..services.form_service import FormService
from ..utils.utils import format_content, translate_role
from ..utils.busines_text import *
from ..config import settings

logger = logging.getLogger(__name__)

async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except QueryIdInvalid:
        pass
    return

async def make_raw_reply_markup(kb: Sequence[Sequence[InlineKeyboardButton]]):
    """
    Конвертирует структуру клавиатуры (список строк, каждая строка — список InlineKeyboardButton)
    в raw.types.ReplyInlineMarkup, который можно передать в functions.messages.SendMessage.
    """
    logger.info("make_raw_reply_markup")
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
    logger.info(f"{callback.from_user.username} validation form start command")
    parts = data.split(':')
    command = parts[1]
    if await form_service.is_submited(user_id, role):
        logger.info(f"{callback.from_user.username} waiting")
        new_message = await callback.message.reply_text(wait_text.replace("{ROLE_NOT_ASSIGNED}", translate_role(role)))
        if session.get('menu_id'):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
        session['menu_id'] = new_message.id
        await sesssion_store.set_overwrite(user_id, session)
        await safe_answer(callback)
        return ""
    expiry = await form_service.is_cooldown(user_id, role)
    if expiry > 0:
        logger.info(f"{callback.from_user.username} cooldown")
        new_message = await callback.message.reply_text(cooldown_text + f"{expiry} минут")
        if session.get('menu_id'):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
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
    logger.info(f"{user.username} callback router received callback:{data}")
    session = await sesssion_store.get(user.id) or {}
    session_role = session.get("definition_id", None)
    parts = data.split(':')

    form_not_match = False

    if data.startswith('operator:') and form_conv.form_def.id == "operator":
        command = await valid_start_role(client, form_service, callback, session, sesssion_store, user.id, "operator",
                                         data)
        if command == "start":
            logger.info(f"{user.username} callback router accept callback - start operator")
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return None
    elif data.startswith('agent:') and form_conv.form_def.id == "agent":
        command = await valid_start_role(client, form_service, callback, session, sesssion_store, user.id, "agent", data)
        if command == "start":
            logger.info(f"{user.username} callback router accept callback - start agent")
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return None

    else:
        if data.startswith('agent:') or data.startswith('operator:'):
            logger.debug(f"{user.username} form_not_match TRUE")
            form_not_match = True

    if data == "cmd_start":
        logger.info(f"{user.username} callback router accept callback - cmd_start")
        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
            except AttributeError:
                try:
                    await client.delete_messages(callback.message.sender_chat.id, session['menu_id'])
                except Exception:
                    await client.delete_messages(callback.message.from_user.username, session['menu_id'])
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
        logger.info(f"{user.username} callback router accept callback - cmd_start_exec")
        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
        await cmd_start(client, callback.message)
        await safe_answer(callback)
        return False

    elif data.startswith("send_questions:") and form_conv.form_def.id == parts[1]:
        logger.info(f"{user.username} callback router accept callback - send_questions")
        await form_conv._send_page(client, callback.message.chat.id, user.id)
        if session['menu_id']:
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
        await safe_answer(callback)
        return None


    elif session_role and session_role != form_conv.form_def.id:
        logger.info(f"{user.username} callback router reject callback - {session_role} != {form_conv.form_def.id}")

        await safe_answer(callback)
        return None

    elif data.startswith('trouble:'):
        logger.info(f"{user.username} callback router accept callback - trouble")
        _, raw_id = data.split(":")
        form_id = int(raw_id)

        logger.debug(f"{user.username} callback router trouble try get form")
        form = await form_service.get_form(form_id=form_id, status=True)

        if form.role == form_conv.form_def.id:
            logger.info(f"{user.username} callback router trouble get form {form.username}")
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
                logger.info(f"{user.username} callback router trouble send for operator")
                await client.send_message(chat_id=form.assigned_to, text=text)
            elif form.role == "agent":
                logger.info(f"{user.username} callback router trouble send for agent")
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
                logger.info(f"{user.username} callback router accept callback - start fill page {page} : {form_name}")
                session["run"] = True
                pages = list(form_conv.form_def.pages())
                session["question"] = 0
                for question in pages[session['page']]:
                    all_answeres = list(session["answers"].keys())
                    for key in all_answeres:
                        if question.key == key:
                            session["question"] += 1
                session['page'] = page

                if session['menu_id']:
                    try:
                        await client.delete_messages(callback.message.chat.id, session['menu_id'])
                    except MessageIdInvalid:
                        pass

                if len(pages[page]) <= session["question"]:
                    logger.warning(f"{user.username} callback router start fill page - clear all answers")
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
                logger.info(f"{user.username} callback router reject callback - fill page, because {form_name} != {form_conv.form_def.id}")
            await safe_answer(callback)
            return None
        elif data.startswith('nav:'):
            action = parts[1]
            form_name = parts[2]
            if form_name == form_conv.form_def.id:
                logger.info(f"{user.username} callback router accept nav {action} {form_name}")
                if action == 'next':
                    logger.info(f"{user.username} callback router nav action next")
                    session['page'] = session.get('page', 0) + 1
                    pages = list(form_conv.form_def.pages())
                    session["question"] = 0
                    for question in pages[session['page']]:
                        all_answeres = list(session["answers"].keys())
                        for key in all_answeres:
                            if question.key == key:
                                session["question"] += 1
                else:
                    logger.info(f"{user.username} callback router nav action prev")
                    if (session.get('page', 0) - 1) < 0:
                        if session['menu_id']:
                            try:
                                await client.delete_messages(callback.message.chat.id, session['menu_id'])
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
                logger.debug(f"{user.username} callback router nav, now session['run'] = False")
                session["run"] = False
                await sesssion_store.set_overwrite(user.id, session)
                await form_conv._send_page(client, callback.message.chat.id, user.id)
            else:
                logger.info(f"{user.username} callback router reject callback - nav, because {form_name} != {form_conv.form_def.id}")

            await callback.answer()
            return None
        elif data == 'submit:confirm':
            logger.info(f"{user.username} callback router accept submit:confirm")
            form = await form_service.create_draft(user.id, user.username, session.get('definition_id', "UNDEFINED"), session.get('answers', {}))
            await form_service.submit_form(form)
            session = await sesssion_store.pop(user.id)
            if session['menu_id']:
                try:
                    await client.delete_messages(callback.message.chat.id, session['menu_id'])
                except MessageIdInvalid:
                    pass
            role_txt = translate_role(session.get("definition_id", ""))

            new_message = await callback.message.reply(anketa_sent.replace("{ROLE_NOT_ASSIGNED}", role_txt))
            session['menu_id'] = new_message.id
            await sesssion_store.set_overwrite(user.id, session)
            #await cmd_start(client, callback.message)
            if session.get('definition_id', "UNDEFINED") == 'agent':
                logger.info(f"{user.username} callback router submit:confirm interpreted agent")
                header = (
                    f"🆔 Заявка #{form.id} ({"Чётная" if form.id & 1 == 0 else "Не чётная"}) ({form.assigned_to})\n"
                    f"🧑‍💼 Роль: {form.role}\n"
                    f"📌 От: @{form.username} (id: {form.user_id})\n"
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
                                             topic_init_msg_id=settings.agent_group_id, text=text, kb=kb)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await send_text_to_topic(client=client, chat_id=settings.group_id,
                                             topic_init_msg_id=settings.agent_group_id, text=text, kb=kb)
                except Forbidden:
                    logger.error("Бот не имеет прав писать в эту группу или был исключён.")
                except Exception as e:
                    logger.error("Ошибка при отправке:", e)
            elif session.get('definition_id', "UNDEFINED") == 'operator':
                logger.info(f"{user.username} callback router submit:confirm interpreted operator")
                target=""
                count = await sesssion_store.pop_other(form.assigned_to)
                await sesssion_store.set_other(form.assigned_to, int(count)+1)
                for key, val in MODER_USERNAMES.items():
                    if val == form.assigned_to:
                        target = key
                await client.send_message(chat_id=target, text=operator_new_anketa.replace("{ASSIGNED_TO NOT ASSIGNED}", form.assigned_to).replace("{COUNT NOT ASSIGNED}", int(count)+1))
                count = await sesssion_store.set_other(key=form.assigned_to, value=int(count)+1)
            await safe_answer(callback)
            return None
        else:
            if not form_not_match:
                logger.info(f"{user.username} callback router reject callback form_not_match")
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

async def callback_global_router(client: Client, callback: CallbackQuery, form_service: FormService, sesssion_store: RedisSessionStore):
    data_g = callback.data or ''
    user = callback.from_user
    logger.info(f"{user.username} global callback router received {data_g}")
    if data_g.startswith('info:'):
        _, action = data_g.split(':')
        logger.info(f"{user.username} global callback router accept info:")
        session = await sesssion_store.get(user.id) or {}

        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass

        kb = [[InlineKeyboardButton("назад", callback_data="cmd_start")]]

        if action == "info":
            logger.info(f"{user.username} global callback router info: interpreted info")
            kb.append([InlineKeyboardButton("Оставить обращение", callback_data="info:request")])

            new_message = await callback.message.reply(base_info, reply_markup=InlineKeyboardMarkup(kb))
        elif action == "request":
            logger.info(f"{user.username} global callback router info: interpreted request")
            kb.append([InlineKeyboardButton("Партнёрство", callback_data="info:partner"),
              InlineKeyboardButton("Обращение", callback_data="info:message")])
            kb.append([InlineKeyboardButton("Помощь", callback_data="info:help")])
            new_message = await callback.message.reply(request_info, reply_markup=InlineKeyboardMarkup(kb))
        elif action == "partner":
            logger.info(f"{user.username} global callback router info: interpreted partner")
            new_message = await callback.message.reply(partner_info, reply_markup=InlineKeyboardMarkup(kb))
            await send_text_to_topic(client, settings.group_id, settings.partner_group_id, f"@{user.username} Заявляет о желании в партнёрстве, напишите в лс")
        elif action == "message":
            logger.info(f"{user.username} global callback router info: interpreted message")
            new_message = await callback.message.reply(message_info, reply_markup=InlineKeyboardMarkup(kb))
            await send_text_to_topic(client, settings.group_id, settings.message_group_id,
                                      f"@{user.username} Хочет передать обращение, напишите в лс")
        else: # always help!
            logger.info(f"{user.username} global callback router info: interpreted help")
            new_message = await callback.message.reply(help_info, reply_markup=InlineKeyboardMarkup(kb))
            await send_text_to_topic(client, settings.group_id, settings.help_group_id,
                                      f"@{user.username} Необходима ПОМОЩЬ, напишите в лс")
        if not session:
            await sesssion_store.set_initialize(user.id, session)
        session['menu_id'] = new_message.id
        await sesssion_store.set_overwrite(user.id, session)
        await safe_answer(callback)

    elif data_g.startswith('deny_reason:'):
        form_id = 0
        try:
            _, raw_id, reason = data_g.split(":")
            form_id = int(raw_id)
        except Exception:
            logger.error(f"{user.username} global callback router invalid data")
            await callback.answer("Неправильные данные", show_alert=True)
            return

        logger.info(f"{user.username} global callback router accept deny_reason")

        form = await form_service.get_form(form_id=form_id)

        user_id = form.user_id

        deny_text = ""
        deny_key = ""

        i = 0
        give_a_new_rec = ""
        cooldown = True
        match form.role:
            case "agent":
                for key, text in agent_deny_reasons_text.items():
                    if key != "Клишированный отказ":
                        cooldown = False
                    if i == int(reason):
                        deny_text = text
                        deny_key = key
                    i += 1
                give_a_new_rec = "operator"
            case "operator":
                for key, text in operator_deny_reasons_text.items():
                    if key != "Клишированный отказ":
                        cooldown = False
                    if i == int(reason):
                        deny_text = text
                        deny_key = key
                    i += 1
                give_a_new_rec = "agent"

        text_to_user = deny_text
        logger.debug(f"{user.username} global callback router deny_reason {form.role} - {deny_key} = {reason}, give_a_new_rec {give_a_new_rec}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Интересно!", callback_data=f"{give_a_new_rec}:start")]])
        await safe_send_to_user(client, user_id, text_to_user, reply_markup_v=kb)

        await form_service.update_form(form_id, None, False, cooldown=cooldown)

        try:
            await callback.answer(f"Заявка ❌ Отклонена", show_alert=True)
        except Exception:
            pass

        try:
            existing_text = callback.message.text or ""
            new_text = existing_text + f"\nПричина: {deny_key}"
            await callback.message.edit_text(new_text)
            await callback.message.edit_reply_markup(None)
        except Exception:
            logger.warning("global callback router deny_reason failed to edit message")
    elif data_g.startswith('form:'):
        form_id = 0
        try:
            _, raw_id, action = data_g.split(":")
            form_id = int(raw_id)
        except Exception:
            logger.info(f"{user.username} global callback router reject form: invalid data")
            await callback.answer("Неправильные данные", show_alert=True)
            return

        form = await form_service.get_form(form_id=form_id)
        if not form:
            logger.info(f"{user.username} global callback router reject form: form not found")
            await callback.answer("Заявка не найдена или уже обработана.", show_alert=True)
            return

        if form.status is not None:
            logger.info(f"{user.username} global callback router reject form: {form.status} is not None")
            await callback.answer("Эта заявка уже обработана.", show_alert=True)
            try:
                await callback.message.edit_reply_markup(None)
            except Exception:
                pass
            return

        logger.info(f"{user.username} global callback router accept form:")

        new_status = True if action == "accept" else False

        status_label = "✅ Успешна" if new_status else "❌ Отклонена"

        # {f'Назначено {form.assigned_to}' if new_status and form.role != "operator" else ' '}
        if new_status:
            await form_service.update_form(form_id, None, new_status)
            try:
                await callback.answer(f"Заявка {status_label}", show_alert=True)
            except Exception:
                pass
        try:
            existing_text = callback.message.text or ""
            new_text = existing_text + f"\n\n🟦 Статус: {status_label}"
            await callback.message.edit_text(new_text)
            await callback.message.edit_reply_markup(None)
        except Exception:
            logger.warning("global callback router form: failed to edit message")

        user_id = form.user_id
        role = (form.role or "").lower()
        assigned = form.assigned_to or ""

        if role == "operator":
            logger.info(f"{user.username} global callback router form: interpreted role as operator")
            if not new_status:  # Отклонено
                kb = [[]]
                i = 0
                for k, v in operator_deny_reasons_text.items():
                    kb[0].append(InlineKeyboardButton(f"❌ {k}", callback_data=f"deny_reason:{form.id}:{i}"))
                    i += 1
                await callback.message.edit_reply_markup(InlineKeyboardMarkup(kb))
            else:  # Успешно
                manager_ref = f"@{assigned}" if assigned else "(менеджер не назначен)"
                await safe_send_to_user(client, user_id, operator_accept.replace("{ASSIGNED_TO NOT ASSIGNED}", manager_ref), InlineKeyboardMarkup([[InlineKeyboardButton(text="Не могу написать", callback_data=f"trouble:{form.id}")]]))

        elif role == "agent":
            logger.info(f"{user.username} global callback router form: interpreted role as agent")
            if not new_status:  # Отклонено
                #
                kb = [[]]
                i = 0
                for k, v in agent_deny_reasons_text.items():
                    kb[0].append(InlineKeyboardButton(f"❌ {k}", callback_data=f"deny_reason:{form.id}:{i}"))
                    i += 1
                await callback.message.edit_reply_markup(InlineKeyboardMarkup(kb))
            else:
                if assigned == MODER_USERNAMES.get("boobsmarley"):
                    text = agent_accept_nastavnik.replace("{ASSIGNED_TO NOT ASSIGNED}", "BoobsMarley")
                else:
                    text = agent_accept
                await safe_send_to_user(client, user_id, text, InlineKeyboardMarkup([[InlineKeyboardButton(text="Не могу написать", callback_data=f"trouble:{form.id}")]]))
            '''
            DEPRECATED
            else:  # Успешно: отправляем полную анкету назначенному менеджеру
                if assigned:
                    manager_target = f"@{assigned}"
                    # формируем сообщение для менеджера: полная анкета + контакт
                    manager_text = (
                            f"Новая успешная заявка (#{form_id}) от @{form.username} (id:{user_id}).\n\n"
                            "📋 Анкета:\n" + format_content(form.content or {})
                    )
                    sent_ok = False

                    try:
                        await client.send_message(chat_id=manager_target, text=manager_text)
                        sent_ok = True
                    except Exception:
                        sent_ok = False

                    if sent_ok:
                        await safe_send_to_user(user_id,
                                                "Ваша заявка одобрена — менеджер получил анкету и свяжется с вами.")
                    else:
                        await callback.message.reply(f'НЕ УДАЛОСЬ ОТПРАВИТЬ АНКЕТУ МЕНЕДЖЕРУ {manager_target}!!')
                else:
                    await callback.message.reply('МЕНЕДЖЕР НЕ НАЗНАЧЕН, АНКЕТА НЕ ОТПРАВЛЕНА МЕНЕДЖЕРУ!!')
                await safe_send_to_user(user_id,
                                        "Ваша заявка одобрена — менеджер получил анкету и свяжется с вами.")
            '''
        else:
            logger.info(f"{user.username} global callback router reject: 404")
            await safe_send_to_user(client, user_id, f"Статус вашей заявки: {status_label}")
    return

logger.info("Thaumaturge IMPORTED")