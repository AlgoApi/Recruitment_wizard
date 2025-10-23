import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import MessageIdInvalid, QueryIdInvalid, FloodWait, Forbidden
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from .form_handler import FormConversation
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

async def safe_send_to_user(client:Client, user_identifier, text_vv, reply_markup_v:InlineKeyboardMarkup=None):
            try:
                await client.send_message(chat_id=user_identifier, text=text_vv, reply_markup=reply_markup_v)
                return True
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения пользователю: {e}")
                return False

async def valid_start_role(client:Client, form_service: FormService, callback: CallbackQuery, session:dict, session_store:RedisSessionStore, user_id, role, data):
    parts = data.split(':')
    command = parts[1]
    if await form_service.is_submited(user_id, role):
        new_message = await callback.message.reply_text(wait_text)
        if session.get('menu_id'):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
        session['menu_id'] = new_message.id
        await session_store.set_overwrite(user_id, session)
        await safe_answer(callback)
        return ""
    expiry = await form_service.is_cooldown(user_id, role)
    if expiry > 0:
        new_message = await callback.message.reply_text(cooldown_text + f"{expiry} минут")
        if session.get('menu_id'):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
        session['menu_id'] = new_message.id
        await session_store.set_overwrite(user_id, session)
        await safe_answer(callback)
        return ""

    return command

async def callback_router(client: Client, callback: CallbackQuery, session_store: RedisSessionStore, form_conv: FormConversation, form_service: FormService, cmd_start: callable):
    data = callback.data or ''
    if data.startswith("info"):
        return
    user = callback.from_user
    session = await session_store.get(user.id) or {}
    session_role = session.get("definition_id", None)
    parts = data.split(':')

    form_not_match = False

    if data.startswith('operator:') and form_conv.form_def.id == "operator":
        command = await valid_start_role(client, form_service, callback, session, session_store, user.id, "operator",
                                         data)
        if command == "start":
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return
    elif data.startswith('agent:') and form_conv.form_def.id == "agent":
        command = await valid_start_role(client, form_service, callback, session, session_store, user.id, "agent", data)
        if command == "start":
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return

    else:
        if data.startswith('agent:') or data.startswith('operator:'):
            form_not_match = True

    if data == "cmd_start":
        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
        # await cmd_start()
        await safe_answer(callback)
        return

    elif data.startswith("send_questions:") and form_conv.form_def.id == parts[1]:
        await form_conv._send_page(client, callback.message.chat.id, user.id)
        if session['menu_id']:
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass
        await safe_answer(callback)
        return


    elif session_role and session_role != form_conv.form_def.id:
        await safe_answer(callback)
        return

    elif data.startswith('trouble:'):
        _, raw_id = data.split(":")
        form_id = int(raw_id)

        form = await form_service.get_form(form_id=form_id, status=True)

        if form.role == form_conv.form_def.id:
            header = (
                "**❗НЕ МОЖЕТ НАПИСАТЬ❗**\n"
                f"🆔 Заявка #{form.id} ({"Чётная" if form.id & 1 == 0 else "Не чётная"})\n"
                f"🧑‍💼 Роль: {form.role}\n"
                f"📌 От: @{form.username} (id: {form.user_id})\n"
                f"🕒 Создано: {form.created_at}\n\n"
            )
            content_text = format_content(form.content or {}, form_conv=form_conv)
            text = header + "📋 Анкета:\n" + (content_text or "(пусто)")

            try:
                await client.send_message(chat_id=settings.admin_group_id, text=text)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await client.send_message(chat_id=settings.admin_group_id, text=text)
            except Forbidden:
                logger.error("Бот не имеет прав писать в эту группу или был исключён.")
            except Exception as e:
                logger.error("Ошибка при отправке:", e)

            await callback.message.reply_text(trouble)

        await safe_answer(callback)
        return

    elif session:
        if data.startswith('fill:page:'):
            page = int(parts[2])
            form_name = parts[3]
            if form_name == form_conv.form_def.id:
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
                await session_store.set_overwrite(user.id, session)
            await safe_answer(callback)
            return
        elif data.startswith('nav:'):
            action = parts[1]
            form_name = parts[2]
            if form_name == form_conv.form_def.id:
                if action == 'next':
                    session['page'] = session.get('page', 0) + 1
                    pages = list(form_conv.form_def.pages())
                    session["question"] = 0
                    for question in pages[session['page']]:
                        all_answeres = list(session["answers"].keys())
                        for key in all_answeres:
                            if question.key == key:
                                session["question"] += 1
                else:
                    if (session.get('page', 0) - 1) < 0:
                        if session['menu_id']:
                            try:
                                await client.delete_messages(callback.message.chat.id, session['menu_id'])
                            except MessageIdInvalid:
                                pass
                            await form_conv.start(client, callback)
                            await callback.answer()
                            return
                    session['page'] = session.get('page', 0) - 1
                    pages = list(form_conv.form_def.pages())
                    session["question"] = 0
                    for question in pages[session['page']]:
                        all_answeres = list(session["answers"].keys())
                        for key in all_answeres:
                            if question.key == key:
                                session["question"] += 1
                session["run"] = False
                await session_store.set_overwrite(user.id, session)
                await form_conv._send_page(client, callback.message.chat.id, user.id)
            await callback.answer()
            return
        elif data == 'submit:confirm':
            form = await form_service.create_draft(user.id, user.username, session.get('definition_id', "UNDEFINED"), session.get('answers', {}))
            await form_service.submit_form(form)
            session = await session_store.pop(user.id)
            if session['menu_id']:
                try:
                    await client.delete_messages(callback.message.chat.id, session['menu_id'])
                except MessageIdInvalid:
                    pass
            role_txt = translate_role(session.get("definition_id", ""))

            new_message = await callback.message.reply(anketa_sent.replace("{ROLE_NOT_ASSIGNED}", role_txt))
            session['menu_id'] = new_message.id
            await session_store.set_overwrite(user.id, session)
            #await cmd_start(client, callback.message)
            if session.get('definition_id', "UNDEFINED") == 'agent':
                header = (
                    f"🆔 Заявка #{form.id} ({"Чётная" if form.id & 1 == 0 else "Не чётная"})\n"
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
                    await client.send_message(chat_id=settings.admin_group_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await client.send_message(chat_id=settings.admin_group_id, text=text, reply_markup=InlineKeyboardMarkup(kb))
                except Forbidden:
                    logger.error("Бот не имеет прав писать в эту группу или был исключён.")
                except Exception as e:
                    logger.error("Ошибка при отправке:", e)
            await safe_answer(callback)
            return
        else:
            if not form_not_match:
                await callback.message.reply("Нажми /start <-")
                await safe_answer(callback)
                return
    elif data == 'submit:cancel':
        await callback.message.reply('Отправка отменена.')
        await callback.answer()
        return
    else:
        await callback.message.reply('Нажми /start <- тык')
        await callback.answer()
        return

async def callback_global_router(client: Client, callback: CallbackQuery, form_service: FormService, session_store: RedisSessionStore):
    data = callback.data or ''
    user = callback.from_user
    if data.startswith('info:'):
        session = await session_store.get(user.id) or {}
        new_message = await callback.message.reply(base_info, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("назад", callback_data="cmd_start")]]))
        if not session:
            await session_store.set_initialize(user.id, session)
        session['menu_id'] = new_message.id
        await session_store.set_overwrite(user.id, session)
        await safe_answer(callback)

    elif data.startswith('deny_reason:'):
        form_id = 0
        try:
            _, raw_id, reason = data.split(":")
            form_id = int(raw_id)
        except Exception:
            await callback.answer("Неправильные данные", show_alert=True)
            return

        form = await form_service.get_form(form_id=form_id)

        user_id = form.user_id

        deny_text = ""
        deny_key = ""

        i = 0
        match form.role:
            case "agent":
                for key, text in agent_deny_reasons_text.items():
                    if i == int(reason):
                        deny_text = text
                        deny_key = key
                    i += 1
            case "operator":
                for key, text in operator_deny_reasons_text.items():
                    if i == int(reason):
                        deny_text = text
                        deny_key = key
                    i += 1

        text_to_user = deny_text
        await safe_send_to_user(client, user_id, text_to_user)

        await form_service.update_form(form_id, None, False)

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
            pass
    elif data.startswith('form:'):
        form_id = 0
        try:
            _, raw_id, action = data.split(":")
            form_id = int(raw_id)
        except Exception:
            await callback.answer("Неправильные данные", show_alert=True)
            return

        form = await form_service.get_form(form_id=form_id)
        if not form:
            await callback.answer("Заявка не найдена или уже обработана.", show_alert=True)
            return

        if form.status is not None:
            await callback.answer("Эта заявка уже обработана.", show_alert=True)
            try:
                await callback.message.edit_reply_markup(None)
            except Exception:
                pass
            return

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
            pass

        user_id = form.user_id
        role = (form.role or "").lower()
        assigned = form.assigned_to or ""

        if role == "operator":
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
            if not new_status:  # Отклонено
                #
                kb = [[]]
                i = 0
                for k, v in agent_deny_reasons_text.items():
                    kb[0].append(InlineKeyboardButton(f"❌ {k}", callback_data=f"deny_reason:{form.id}:{i}"))
                    i += 1
                await callback.message.edit_reply_markup(InlineKeyboardMarkup(kb))
            else:
                await safe_send_to_user(client, user_id, agent_accept.replace("{ASSIGNED_TO NOT ASSIGNED}", form.assigned_to), InlineKeyboardMarkup([[InlineKeyboardButton(text="Не могу написать", callback_data=f"trouble:{form.id}")]]))
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
            await safe_send_to_user(client, user_id, f"Статус вашей заявки: {status_label}")
    return
