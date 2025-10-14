import asyncio
import logging
from pyrogram import Client
from pyrogram.errors import MessageIdInvalid, QueryIdInvalid, FloodWait, Forbidden
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from .form_handler import FormConversation
from ..storage.session_store import RedisSessionStore
from ..services.form_service import FormService
from ..utils.utils import format_content
from ..utils.busines_text import *
from ..config import settings

logger = logging.getLogger(__name__)

async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except QueryIdInvalid:
        pass
    return

async def callback_router(client: Client, callback: CallbackQuery, session_store: RedisSessionStore, form_conv: FormConversation, form_service: FormService, cmd_start: callable):
    data = callback.data or ''
    user = callback.from_user
    session = await session_store.get(user.id) or {}
    if data.startswith('operator:') and form_conv.form_def.id == "operator":
        parts = data.split(':')
        command = parts[1]
        if await form_service.is_submited(user.id, "operator"):
            await callback.message.reply_text(wait_text)
            await safe_answer(callback)
            return
        if await form_service.is_cooldown(user.id, "operator"):
            await callback.message.reply_text(cooldown_text)
            await safe_answer(callback)
            return
        if command == "start":
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return
    elif data.startswith('agent:') and form_conv.form_def.id == "agent":
        parts = data.split(':')
        command = parts[1]
        if await form_service.is_submited(user.id, "agent"):
            await callback.message.reply_text(wait_text)
            await safe_answer(callback)
            return
        if await form_service.is_cooldown(user.id, "agent"):
            await callback.message.reply_text(cooldown_text)
            await safe_answer(callback)
            return
        if command == "start":
            await form_conv.start(client, callback)

        await safe_answer(callback)
        return

    elif session.get("definition_id") != form_conv.form_def.id:
        await safe_answer(callback)
        return
    elif session:
        if data.startswith('fill:page:'):
            # user pressed fill — ask for first unanswered field on that page
            parts = data.split(':')
            page = int(parts[2])
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

            # send prompt for first unanswered field
            if len(pages[page]) <= session["question"]:
                # await callback.message.reply("На этой странице всё, переходите к следующей")
                for question in pages[page]:
                    all_answeres = list(session["answers"].keys())
                    for key in all_answeres:
                        if question.key == key:
                            session["answers"].pop(key)
                            session["question"] -= 1
            await session_store.set_overwrite(user.id, session)
            await form_conv._send_page(client, callback.message.chat.id, user.id)
            await callback.message.reply(f'Отправьте {pages[page][session["question"]].label}')
            await safe_answer(callback)
            return
        if data.startswith('nav:'):
            action = data.split(':')[1]
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
                session['page'] = max(0, session.get('page', 0) - 1)
                pages = list(form_conv.form_def.pages())
                session["question"] = 0
                for question in pages[session['page']]:
                    all_answeres = list(session["answers"].keys())
                    for key in all_answeres:
                        if question.key == key:
                            session["question"] += 1
            session["run"] = False
            await session_store.set_overwrite(user.id, session)
            await callback.answer()
            await form_conv._send_page(client, callback.message.chat.id, user.id)
            return
        if data == 'submit:confirm':
            form = await form_service.create_draft(user.id, user.username, session.get('definition_id', "UNDEFINED"), session.get('answers', {}))
            await form_service.submit_form(form)
            session = await session_store.pop(user.id)
            if session['menu_id']:
                try:
                    await client.delete_messages(callback.message.chat.id, session['menu_id'])
                except MessageIdInvalid:
                    pass
            await callback.message.reply(anketa_sent)
            await cmd_start(client, callback.message)
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
                    await client.send_message(chat_id=int(settings.admin_group_id), text=text, reply_markup=InlineKeyboardMarkup(kb))
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await client.send_message(chat_id=int(settings.admin_group_id), text=text, reply_markup=InlineKeyboardMarkup(kb))
                except Forbidden:
                    print("Бот не имеет прав писать в эту группу или был исключён.")
                except Exception as e:
                    print("Ошибка при отправке:", e)
            await safe_answer(callback)

            return
    elif data == 'submit:cancel':
        await callback.message.reply('Отправка отменена.')
        await callback.answer()
        return
    else:
        await callback.message.reply('Отправьте /start <- тык')
        await callback.answer()
        return

async def callback_global_router(client: Client, callback: CallbackQuery, form_service: FormService):
    data = callback.data or ''
    user = callback.from_user
    if data.startswith('info:'):
        await callback.message.reply(base_info)
        await callback.answer()

    elif data.startswith('deny_reason:'):
        form_id = 0
        try:
            _, raw_id, reason = data.split(":")
            form_id = int(raw_id)
        except Exception:
            await callback.answer("Неправильные данные", show_alert=True)
            return

        async def safe_send_to_user(user_identifier, text_v):
            try:
                await client.send_message(chat_id=user_identifier, text=text_v)
                return True
            except Exception:
                return False

        form = await form_service.get_form(form_id=form_id)

        user_id = form.user_id

        left, sep, right = agent_desc.partition("!")

        deny_text = ""
        deny_key = ""

        i = 0
        for key, text in operator_deny_reasons_text.items():
            if i == int(reason):
                deny_text = text
                deny_key = key
            i += 1

        text_to_user = deny_text + right if sep == "!" else deny_text + agent_desc
        await safe_send_to_user(user_id, text_to_user)

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

        async def safe_send_to_user(user_identifier, text_vv):
            try:
                await client.send_message(chat_id=user_identifier, text=text_vv)
                return True
            except Exception:
                return False

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
                await safe_send_to_user(user_id, operator_accept + manager_ref)

        elif role == "agent":
            if not new_status:  # Отклонено
                await form_service.update_form(form_id, None, new_status)
                left, sep, right = operator_desc.partition("!")
                await safe_send_to_user(user_id, agent_reject + right if sep == "!" else agent_reject + operator_desc)
            else:
                await safe_send_to_user(user_id, agent_accept)
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
            await safe_send_to_user(user_id, f"Статус вашей заявки: {status_label}")
    return
