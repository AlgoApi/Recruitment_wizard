import asyncio
import html
import json

from pyrogram.enums import ParseMode

from .callbacks import send_text_to_topic
from pyrogram import Client
from pyrogram.errors import MessageIdInvalid, QueryIdInvalid
from aiohttp import ClientResponseError
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ..config import settings
from ..security.security_rules import MODER_USERNAMES
from ..services.form_service import FormService
from ..services.staff_service import StaffService
from ..services.user_service import UserService
from ..storage.session_store import RedisSessionStore
from ..utils.busines_text import *
from ..utils.utils import assign_master

logger = logging.getLogger(__name__)

async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except QueryIdInvalid:
        pass
    return

async def safe_send_to_user(client: Client, user_identifier, text_vv, reply_markup_v: InlineKeyboardMarkup = None):
    try:
        await client.send_message(chat_id=user_identifier, text=text_vv, reply_markup=reply_markup_v)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю: {e}")
        return False

async def callback_global_router(client: Client, callback: CallbackQuery, form_service: FormService, sesssion_store: RedisSessionStore, user_service: UserService, staff_service:StaffService):
    data_g = callback.data or ''
    user = callback.from_user
    logger.info(f"{user.username or user.id} {user.first_name} global callback router received {data_g}")
    if data_g.startswith('info:'):
        _, action = data_g.split(':')
        logger.info(f"{user.username or user.id} {user.first_name} global callback router accept info:")
        session = await sesssion_store.get(user.id) or {}

        if session.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, session['menu_id'])
            except MessageIdInvalid:
                pass

        kb = [[InlineKeyboardButton("назад", callback_data="cmd_start")]]

        if action == "info":
            logger.info(f"{user.username or user.id} {user.first_name} global callback router info: interpreted info")
            kb.append([InlineKeyboardButton("Оставить обращение", callback_data="info:request")])

            new_message = await callback.message.reply(base_info, reply_markup=InlineKeyboardMarkup(kb))
        elif action == "request":
            logger.info(f"{user.username or user.id} {user.first_name} global callback router info: interpreted request")
            kb.append([InlineKeyboardButton("Партнёрство", callback_data="info:partner"),
              InlineKeyboardButton("Обращение", callback_data="info:message")])
            kb.append([InlineKeyboardButton("Помощь", callback_data="info:help")])
            new_message = await callback.message.reply(request_info, reply_markup=InlineKeyboardMarkup(kb))
        elif action == "partner":
            logger.info(f"{user.username or user.id} {user.first_name} global callback router info: interpreted partner")
            new_message = await callback.message.reply(partner_info, reply_markup=InlineKeyboardMarkup(kb))
            await send_text_to_topic(client, settings.group_id, settings.partner_group_id, f"{user.first_name} @{user.username or user.id} Заявляет о желании в партнёрстве, напишите в лс")
        elif action == "message":
            logger.info(f"{user.username or user.id} {user.first_name} global callback router info: interpreted message")
            new_message = await callback.message.reply(message_info, reply_markup=InlineKeyboardMarkup(kb))
            await send_text_to_topic(client, settings.group_id, settings.message_group_id,
                                      f"{user.first_name} @{user.username or user.id} Хочет передать обращение, напишите в лс")
        else: # always help!
            logger.info(f"{user.username or user.id} {user.first_name} global callback router info: interpreted help")
            new_message = await callback.message.reply(help_info, reply_markup=InlineKeyboardMarkup(kb))
            await send_text_to_topic(client, settings.group_id, settings.help_group_id,
                                      f"{user.first_name} @{user.username or user.id} Необходима ПОМОЩЬ, напишите в лс")
        if not session:
            await sesssion_store.set_initialize(user.id, session)
        session['menu_id'] = new_message.id
        await sesssion_store.set_overwrite(user.id, session)
        await safe_answer(callback)
        return True

    elif data_g.startswith('deny_reason:'):
        form_id = 0
        try:
            _, raw_id, reason = data_g.split(":")
            form_id = int(raw_id)
        except Exception:
            logger.error(f"{user.username or user.id} {user.first_name} global callback router invalid data")
            await callback.answer("Неправильные данные", show_alert=True)
            return False

        logger.info(f"{user.username or user.id} {user.first_name} global callback router accept deny_reason")

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

        text_to_user = deny_text.replace("{FIRSTNAME_NOT_ASSIGNED}", user.first_name)
        logger.debug(f"{user.username or user.id} {user.first_name} global callback router deny_reason {form.role} - {deny_key} = {reason}, give_a_new_rec {give_a_new_rec}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Интересно!", callback_data=f"{give_a_new_rec}:start")]])
        await safe_send_to_user(client, user_id, text_to_user, reply_markup_v=kb)

        assigned = await assign_master(staff_service, form.role, user_id)
        await form_service.update_form(form_id, status=False, assign=assigned, cooldown=cooldown)

        try:
            await callback.answer(f"Заявка ❌ Отклонена", show_alert=True)
        except Exception:
            pass

        existing_text = callback.message.text or ""
        new_text = existing_text + f"\n\nПричина: {deny_key}" + f"\n🟦 Статус: ❌ Отклонена"
        await callback.message.edit_text(new_text.replace("(нет решения)", f"({assigned})"))
        try:
            await callback.message.edit_reply_markup(None)
        except Exception:
            pass

        return True
    elif data_g.startswith('form:'):
        form_id = 0
        try:
            _, raw_id, action = data_g.split(":")
            form_id = int(raw_id)
        except Exception:
            logger.info(f"{user.username or user.id} {user.first_name} global callback router reject form: invalid data")
            await callback.answer("Неправильные данные", show_alert=True)
            return False

        form = await form_service.get_form(form_id=form_id)
        if not form:
            logger.info(f"{user.username or user.id} {user.first_name} global callback router reject form: form not found")
            await callback.answer("Заявка не найдена или уже обработана.", show_alert=True)
            return False

        if form.status is not None:
            logger.info(f"{user.username or user.id} {user.first_name} global callback router reject form: {form.status} is not None")
            await callback.answer("Эта заявка уже обработана.", show_alert=True)
            try:
                await callback.message.edit_reply_markup(None)
            except Exception:
                pass
            return True

        logger.info(f"{user.username or user.id} {user.first_name} global callback router accept form:")

        new_status = True if action == "accept" else False

        status_label = "✅ Успешна" if new_status else "❌ Отклонена"

        role = (form.role or "").lower()
        assigned = form.assigned_to or ""

        user_id = form.user_id

        if role == "operator":
            logger.info(f"{user.username or user.id} {user.first_name} global callback router form {form.user_id}: interpreted role as operator")
            if not new_status:  # Отклонено
                kb = []
                i = 0
                for k, v in operator_deny_reasons_text.items():
                    kb.append([InlineKeyboardButton(f"❌ {k}", callback_data=f"deny_reason:{form.id}:{i}")])
                    i += 1
                await callback.message.edit_reply_markup(InlineKeyboardMarkup(kb))
            else:  # Успешно
                assigned = await assign_master(staff_service, role, user_id)

                existing_text = callback.message.text or ""
                new_text = existing_text + f"\n\n🟦 Статус: {status_label}"
                await callback.message.edit_text(new_text.replace("(нет решения)", f"({assigned})"))
                try:
                    await callback.message.edit_reply_markup(None)
                except Exception:
                    pass

                await staff_service.update_form(find_username=assigned, find_role="moderator", operator_need=False)
                await form_service.update_form(form_id, status=new_status, assign=assigned)
                manager_ref = f"@{assigned}" if assigned else "(менеджер не назначен)"
                target = ""
                for key, val in MODER_USERNAMES.items():
                    if val == assigned:
                        target = key
                escaped_username = html.escape(form.username)
                await client.send_message(chat_id=target, text=operator_new_anketa.replace("{ASSIGNED_TO NOT ASSIGNED}", assigned).replace("{CRED NOT ASSIGNED}", f"<pre>{user_id}</pre> или <pre>{escaped_username}</pre>"), parse_mode=ParseMode.HTML)
                await safe_send_to_user(client, user_id, operator_accept.replace("{ASSIGNED_TO NOT ASSIGNED}", manager_ref), InlineKeyboardMarkup([[InlineKeyboardButton(text="Не могу написать", callback_data=f"trouble:{form.id}")]]))
            return True

        elif role == "agent":
            logger.info(f"{user.username or user.id} {user.first_name} global callback router form {form.user_id}: interpreted role as agent")
            if not new_status:  # Отклонено
                #
                kb = []
                i = 0
                for k, v in agent_deny_reasons_text.items():
                    kb.append([InlineKeyboardButton(f"❌ {k}", callback_data=f"deny_reason:{form.id}:{i}")])
                    i += 1
                await callback.message.edit_reply_markup(InlineKeyboardMarkup(kb))
            else:
                assigned = await assign_master(staff_service, role, user_id)

                existing_text = callback.message.text or ""
                new_text = existing_text + f"\n\n🟦 Статус: {status_label}"
                new_text = new_text.replace("(нет решения)", f"({assigned})")
                target_crm = "drippineveryday"

                if assigned == MODER_USERNAMES.get("boobsmarley"):
                    client_text = agent_accept_nastavnik.replace("{ASSIGNED_TO NOT ASSIGNED}", "BoobsMarley")
                    target_crm = "boobsmarley"
                else:
                    client_text = agent_accept
                auto_save_result = "UNDEFINED"
                try:
                    auto_save_result = await form_service.auto_save_agent_to_crm(form_id, target_crm)
                except ClientResponseError as e:
                    logger.warning(f"{user.username or user.id} {user.first_name} auto_save_agent_to_crm failed: {e.status}")
                    new_text = new_text + f"\n❗Требуется завести данные в CRM вручную❗\n Причина: {e}"
                except Exception as e:
                    logger.error(f"{user.username or user.id} {user.first_name} auto_save_agent_to_crm failed: {e}")
                    new_text = new_text+f"\n❗Требуется завести данные в CRM вручную❗\n Причина: {e}"

                logger.info(f"Auto save to crm complited: {auto_save_result}")

                await callback.message.edit_text(new_text)
                try:
                    await callback.message.edit_reply_markup(None)
                except Exception:
                    pass

                await staff_service.update_form(find_username=assigned, find_role="moderator", agent_need=False)
                await form_service.update_form(form_id, status=new_status, assign=assigned)
                for k, v in MODER_USERNAMES.items():
                    if v == assigned:
                        try:
                            await safe_send_to_user(client, k, new_text)
                        except Exception:
                            logger.error(f"{user.username or user.id} {user.first_name} global callback router form {role} {form.user_id} accepted, but cannot send info to assigned admin")
                        break

                await safe_send_to_user(client, user_id, client_text, InlineKeyboardMarkup([[InlineKeyboardButton(text="Не могу написать", callback_data=f"trouble:{form.id}")]]))

            return True
        else:
            logger.error(f"{user.username or user.id} {user.first_name} global callback router reject: 404")
            await safe_send_to_user(client, user_id, f"Статус вашей заявки: {status_label}")
            return True

    elif data_g.startswith('spam'):
        async def get_last_msg(alarm=True):
            msg = await client.get_messages(callback.from_user.id, callback.message.id+1)
            if msg and msg.from_user and msg.from_user.is_bot:
                msg = await client.get_messages(callback.from_user.id, callback.message.id+2)
            catched_text = "NONE"
            if msg.text or msg.caption:
                catched_text = (msg.text or msg.caption)[:50]
            if not msg or not msg.from_user or msg.from_user.is_bot:
                if alarm:
                    await callback.message.reply(f"проверьте наличие Вашего сообщения")
                    try:
                        logger.warning(f"get_last_msg for spam: {catched_text}")
                    except TypeError:
                        logger.warning(f"get_last_msg for spam: {catched_text}")
                return None
            logger.info(f"get_last_msg for spam: {catched_text}")
            return msg

        async def get_tittle_btn(callback_data:str, target:str="url(ссылку)"):
            msg = await get_last_msg()
            if msg:
                if msg.text == "exit":
                    return True
                data_spam = await sesssion_store.get_other(key=f"{callback.from_user.id}:spam") or dict()
                found = False
                inc = 0
                while inc < 3:
                    if data_spam.get(f"title{inc}"):
                        inc += 1
                    else:
                        found = True
                        break
                if found:
                    data_spam.update({f"title{inc}": msg.text})
                    await sesssion_store.set_other(key=f"{callback.from_user.id}:spam", value=json.dumps(data_spam))
                    kb = [[InlineKeyboardButton(text="Отправил", callback_data=callback_data)]]
                    text = f"Отправьте {target} кнопки, если хотите прервать напишите 'exit'"
                    await callback.message.reply(text, reply_markup=InlineKeyboardMarkup(kb))
                    return True
                else:
                    await callback.message.reply("Попробуйте ещё раз, может уже максиму 3 кнопким?")
                    return True
            else:
                await callback.message.reply("Попробуйте ещё раз, может уже максимум 3 кнопки?")
                return True

        async def get_url_btn(callback_data:str, target:str="название", mode:str="url"):
            msg = await get_last_msg()
            if msg:
                if msg.text == "exit":
                    return True
                data_spam = await sesssion_store.get_other(key=f"{callback.from_user.id}:spam") or dict()
                found = False
                inc = 0
                while inc < 3:
                    if data_spam.get(f"url{inc}"):
                        inc += 1
                    else:
                        found = True
                        break
                if found:
                    data_spam.update({f"url{inc}": msg.text})
                    data_spam.update({f"mode": mode})
                    await sesssion_store.set_other(key=f"{callback.from_user.id}:spam", value=json.dumps(data_spam))
                    await default_answer()
                    return True
                else:
                    await callback.message.reply("Попробуйте ещё раз, может уже максимум 3 кнопки?")
                    return True
            else:
                await callback.message.reply("Попробуйте ещё раз, может уже максимум 3 кнопки?")
                return True

        async def default_answer():
            kb = [[InlineKeyboardButton(text="Отправил", callback_data="spam:url:title_btn")]]
            inc = 0
            data_spam = await sesssion_store.get_other(key=f"{callback.from_user.id}:spam") or dict()
            text = "Отправьте название кнопки, если хотите прервать напишите 'exit'"
            found = False
            while inc < 3:
                if data_spam.get(f"title{inc}"):
                    found = True
                    break
                inc += 1
            if found:
                text = "Чтобы закончить добавление кнопок нажмите кнопку 'Готово'\n" + text
                kb.append([InlineKeyboardButton(text="Готово", callback_data="spam:content")])
            await callback.message.reply(text, reply_markup=InlineKeyboardMarkup(kb))

        data_g = data_g.split(':')
        match data_g[1]:
            case "url":
                match data_g[2]:
                    case "title_btn":
                        await get_tittle_btn(callback_data="spam:url:url_btn")
                    case "url_btn":
                        await get_url_btn(callback_data="spam:url:title_btn")
                    case _:
                        await default_answer()
            case "callback":
                match data_g[2]:
                    case "title_btn":
                        await get_tittle_btn(callback_data="spam:callback:url_btn", target="точку входа")
                    case "url_btn":
                        await get_url_btn(callback_data="spam:callback:title_btn", mode="callback")
                    case _:
                        await default_answer()
            case "content":
                msg = await get_last_msg(alarm=False)
                if msg:
                    if msg.text == "exit":
                        return True
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(text="Отправил", callback_data="spam:send")]])
                await callback.message.reply("Отправьте текст сообщения с медиа, если хотите прервать напишите 'exit'", reply_markup=kb)
            case "send":
                msg = await get_last_msg()
                if msg:
                    if msg.text == "exit":
                        return True

                    data_spam = await sesssion_store.get_other(key=f"{callback.from_user.id}:spam") or dict()
                    kb = []
                    if data_spam.get("mode") == "callback" and data_spam.get("url0"):
                        for i in range(3):
                            if data_spam.get(f"title{i}"):
                                kb.append([InlineKeyboardButton(text=data_spam.get(f"title{i}", "Упс, что-то пошло не так"), callback_data=data_spam.get(f"url{i}", "example.com"))])
                        kb = InlineKeyboardMarkup(kb)
                    elif data_spam.get("mode") == "url" and data_spam.get("url0"):
                        for i in range(3):
                            if data_spam.get(f"title{i}"):
                                kb.append(
                                    [InlineKeyboardButton(text=data_spam.get(f"title{i}", "Упс, что-то пошло не так"), url=data_spam.get(f"url{i}", "example.com"))])
                        kb = InlineKeyboardMarkup(kb)
                    else:
                        kb = None

                    accepted_rassilok = 0
                    rejected_rassilok = 0
                    copy_message_id = callback.message.id + 1
                    await callback.message.reply("Рассылка началась")

                    msg = await client.get_messages(callback.message.chat.id, copy_message_id)
                    if msg and msg.from_user.is_bot:
                        copy_message_id += 1
                        msg = await client.get_messages(callback.message.chat.id, copy_message_id)
                    if not msg or msg.from_user.is_bot:
                        await callback.message.reply(f"Рассылка окончена.\nпроверьте наличие Вашего сообщения")
                        return True
                    catched_text = "NONE"
                    if msg.text or msg.caption:
                        catched_text = (msg.text or msg.caption)[:50]
                    logger.info(f"{callback.message.from_user.id} start rassilku, kb: {kb}, text: {catched_text}")
                    users = await user_service.get_user(limit=False)

                    for user_entry in users:
                        try:
                            msg = await client.copy_message(chat_id=user_entry.user_id, message_id=copy_message_id,
                                                            from_chat_id=callback.from_user.id, reply_markup=kb)
                            if msg is not None:
                                accepted_rassilok += 1
                            else:
                                rejected_rassilok += 1
                        except Exception:
                            logger.warning(f"Failed to send rassilka to {user_entry.user_id}")
                            rejected_rassilok += 1
                    await callback.message.reply(
                        f"Рассылка окончена.\nотправлено: {accepted_rassilok}, отклонено: {rejected_rassilok}")
                else:
                    await callback.message.reply("Попробуйте ещё раз")
        await safe_answer(callback)
        return True
    return False