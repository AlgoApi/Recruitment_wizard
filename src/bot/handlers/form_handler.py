import logging
import re

from pyrogram import Client
from pyrogram.errors import MessageIdInvalid
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from ..forms.definition import FormDefinition, FieldKind
from ..forms.validators import ValidatorWizard, email_validator, phone_validator, validate_birth_date, validate_no_link
from ..services.form_service import FormService
from ..storage.session_store import RedisSessionStore
from ..utils.utils import translate_role

logger = logging.getLogger(__name__)

class FormConversation:
    def __init__(self, session_store: RedisSessionStore, form_service: FormService, form_def: FormDefinition):
        self.session_store = session_store
        self.form_service = form_service
        self.form_def = form_def
        self.validator = ValidatorWizard()
        self.validator.add_validator(email_validator, "email")
        self.validator.add_validator(phone_validator, "phone")
        self.validator.add_validator(validate_birth_date, "date")
        self.validator.add_validator(validate_no_link, "no_link")
        logger.info(f"init FormConversation for {form_def.id}")

    async def start(self, client: Client, callback: CallbackQuery):
        user = callback.from_user
        logger.info(f"init form conversation {user.username or user.id}  {user.first_name}")
        pages = list(self.form_def.pages())

        session = {
            'run': False,
            'definition_id': self.form_def.id,
            'menu_id': 0,
            'page': 0,
            'question':0,
            'count_questions': 0,
            'count_pages': len(pages),
            'answers': {},
        }
        for _ in pages:
            for __ in _:
                session["count_questions"] += 1

        logger.info(f"{user.username or user.id} {user.first_name} form conversation try get old form")
        session_bd = await self.form_service.get_form(user_id=user.id, role=self.form_def.id, status=True)
        if session_bd:
            session["answers"] = session_bd.content
        logger.info(f"{user.username or user.id} {user.first_name} form conversation try get cached form")
        sessiiion_old = await self.session_store.get(user.id) or {}

        if sessiiion_old.get('menu_id', None):
            try:
                await client.delete_messages(callback.message.chat.id, sessiiion_old['menu_id'])
            except MessageIdInvalid:
                pass

        if sessiiion_old and sessiiion_old.get("definition_id", "") != session["definition_id"]:
            logger.info(f"{user.username or user.id} {user.first_name} form conversation set_overwrite form")
            await self.session_store.set_overwrite(user.id, session)
        else:
            logger.info(f"{user.username or user.id} {user.first_name} form conversation set_initialize form")
            await self.session_store.set_initialize(user.id, session)

        if self.form_def.video:
            new_message = await callback.message.reply_video(video=self.form_def.video, caption=f"{self.form_def.title}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Заполнить анкету!", callback_data=f"send_questions:{session["definition_id"]}")], [InlineKeyboardButton("назад", callback_data="cmd_start")]]))
        else:
            new_message = await callback.message.reply(f"{self.form_def.title}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Заполнить анкету!", callback_data=f"send_questions:{session["definition_id"]}")], [InlineKeyboardButton("назад", callback_data="cmd_start")]]))
        #await self._send_page(client, callback.message.chat.id, user.id)
        session['menu_id'] = new_message.id
        await self.session_store.set_overwrite(user.id, session)

    async def handle_message(self, client: Client, message: Message):
        user = message.from_user
        logger.info(f"{user.username or user.id} {user.first_name} handle_message received message")
        session = await self.session_store.get(user.id) or {}
        if session.get('definition_id') != self.form_def.id:
            logger.info(f"{user.username or user.id} {user.first_name} handle_message rejected message because {session.get('definition_id')} != {self.form_def.id}")
            return
        if not session["run"]:
            logger.info(f"{user.username or user.id} {user.first_name} handle_message rejected message because form filling has not started")
            await message.reply('Нажмите Заполнить/Изменить чтобы начать.')
            return
        if not session:
            logger.info(f"{user.username or user.id} {user.first_name} handle_message rejected message because session not found")
            await message.reply('Сессия не найдена. Наберите /start чтобы начать.')
            return
        page_idx = session.get('page', 0)
        fields = list(self.form_def.pages())
        if page_idx >= len(fields):
            logger.info(f"{user.username or user.id} {user.first_name} handle_message rejected message because page not found")
            await message.reply('Страницы не найдены — начните заново. Наберите /start')
            return

        # Accept input for the next unanswered field on this page
        page_fields = fields[page_idx]
        # find first field without answer
        target = None
        for f in page_fields:
            if f.key not in session['answers']:
                target = f
                break
        if not target:
            # Move forward
            await self._goto_next_page(user.id, client, message.chat.id)
            return

        # Basic validation
        val = None
        if target.kind == 'file' and message.document:
            val = {'file_id': message.document.file_id, 'file_name': message.document.file_name}
        else:
            val = message.text
            if target.kind == FieldKind.NUMBER:
                re_val = re.search(r'\d+', val)
                if re_val:
                    val = int(re_val.group())
                else:
                    logger.info(f"{user.username or user.id} {user.first_name} handle_message rejected message because NAN")
                    await message.reply(f'Так не пойдёт, введите число')
                    return
            logger.info(f"{user.username or user.id} {user.first_name} handle_message try validate message")
            status, validator_message = self.validator.validate_answer(target, val)
            if not status:
                logger.info(f"{user.username or user.id} {user.first_name} handle_message rejected message because validation failed")
                await message.reply(f'Так не пойдёт, {validator_message}')
                return

        if target.required and not val:
            logger.warning(f"{user.username or user.id} {user.first_name} handle_message rejected message because {target.label} not filled")
            await message.reply(f'Поле "{target.label}" обязательно.')
            return

        logger.warning(f"{user.username or user.id} {user.first_name} handle_message accepted message")
        session['answers'][target.key] = val
        session['question'] += 1
        await self.session_store.set_overwrite(user.id, session)

        all_answered = all(f.key in session['answers'] for f in page_fields)
        if all_answered:
            logger.warning(f"{user.username or user.id} {user.first_name} handle_message form pages")
            await self._send_page_controls(client, message.chat.id, user.id, session)
        else:
            logger.info(f"{user.username or user.id} {user.first_name} handle_message try to calc new_needed_vl")
            if session['question'] + 1 > len(page_fields):
                session['question'] = 0
            new_needed_vl = page_fields[session['question']].label
            text = f'{target.label} - принято!\nОтправьте {new_needed_vl}:'
            if new_needed_vl.startswith("phone"):
                text += "||(Если боитесь давать свой личный номер телефона, оформите eSIM или виртуальный номер — он нужен только для регистрации в CRM. Личные данные не требуются)||"
            await message.reply(text)

    async def _send_page(self, client, chat_id: int, user_id: int):
        logger.info(f"{user_id} _send_page form page")
        session = await self.session_store.get(user_id)
        if session is None:
            logger.warning(f"{user_id} warning in 156 line form_handler")
            await client.send_message(chat_id, text="Вышло время ожидания, начните заполнение анкеты снова", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("начать", callback_data="cmd_start")]]))
            return

        session['run'] = False
        page_idx = session['page'] or 0
        logger.info(f"{user_id} _send_page page {page_idx}")
        pages = list(self.form_def.pages())
        if page_idx >= len(pages):
            page_idx =- 1
        page_fields = pages[page_idx]
        del pages

        text_lines = [f'Заполняем {translate_role(session.get("definition_id", ""))}\nСтраница анкеты {page_idx + 1}/{session['count_pages']}\n']
        for f in page_fields:
            existing = session['answers'].get(f.key)
            text_lines.append(f"{f.label}: {existing if existing else '(пусто)'}")
            if f.label.startswith("phone"):
                text_lines.append("\n||(Если боитесь давать свой личный номер телефона, оформите eSIM или виртуальный номер — он нужен только для регистрации в CRM. Личные данные не требуются)||\n")
        text = '\n'.join(text_lines)

        if session['menu_id']:
            try:
                await client.delete_messages(chat_id, session['menu_id'])
            except MessageIdInvalid:
                pass

        kb_unit = []
        kb = []

        if len(session['answers']) >= session['count_questions']:
            kb.append([InlineKeyboardButton('Отправить', callback_data='submit:confirm')])

        kb.append([InlineKeyboardButton('Заполнить/Изменить', callback_data=f'fill:page:{page_idx}:{session["definition_id"]}')])

        kb_unit.append(InlineKeyboardButton('Назад', callback_data=f'nav:prev:{session["definition_id"]}'))
        if session['page'] + 1 < session['count_pages']:
            kb_unit.append(InlineKeyboardButton('Следующая', callback_data=f'nav:next:{session["definition_id"]}'))
        kb.append(kb_unit)

        logger.info(f"{user_id} _send_page send page")
        if page_fields[0].animation:
            sent_message = await client.send_animation(chat_id=chat_id, caption=text, reply_markup=InlineKeyboardMarkup(kb),
                                                   animation=page_fields[0].animation)
        elif page_fields[0].video:
            sent_message = await client.send_video(chat_id=chat_id, caption=text, reply_markup=InlineKeyboardMarkup(kb),
                                                   video=page_fields[0].video)
        elif page_fields[0].photo:
            sent_message = await client.send_photo(chat_id=chat_id, caption=text, reply_markup=InlineKeyboardMarkup(kb),
                                                   photo=page_fields[0].photo)
        else:
            sent_message = await client.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(kb))
        session['menu_id'] = sent_message.id
        await self.session_store.set_overwrite(user_id, session)

    async def _send_page_controls(self, client, chat_id: int, user_id: int, session: dict):
        # After page complete, show navigation and submit
        '''
        kb_unit = []
        kb = []

        kb_unit.append(InlineKeyboardButton('Назад', callback_data=f'nav:prev:{session["definition_id"]}'))
        if session['page'] + 1 < session['count_pages']:
            kb_unit.append(InlineKeyboardButton('Следующая', callback_data=f'nav:next:{session["definition_id"]}'))
        kb.append(kb_unit)
        if len(session['answers']) == session['count_questions']:
            kb.append([InlineKeyboardButton('Отправить', callback_data='submit:confirm')])

        #await self._send_page(client, chat_id, user_id)
        if session['menu_id']:
            try:
                await client.delete_messages(chat_id, session['menu_id'])
            except MessageIdInvalid:
                pass
        sent_message = await client.send_message(chat_id, 'Страница заполнена. Что дальше?', reply_markup=InlineKeyboardMarkup(kb))
        '''

        await self._send_page(client, chat_id, user_id)

    async def _goto_next_page(self, user_id: int, client, chat_id: int):
        session = await self.session_store.get(user_id)
        session['page'] = session.get('page', 0) + 1
        await self.session_store.set_overwrite(user_id, session)
        await self._send_page(client, chat_id, user_id)

logger.info("Spellbinder IMPORTED")