from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..config import settings
from pyrogram.errors import UserNotParticipant, FloodWait, Forbidden

MODER_USERNAMES = dict()
ADMIN_USERNAMES = dict()

def moder_rule_fabric():
    return filters.create(lambda _, __, message: (
        bool(message.from_user and (message.from_user.username or "").lower() in {u.lower() for u in list(MODER_USERNAMES.values())})
    ))

def admin_rule_fabric():
    return filters.create(lambda _, __, message: (
        bool(message.from_user and (message.from_user.username or "").lower() in {u.lower() for u in list(ADMIN_USERNAMES.values())})
    ))

def superadmin_rule_fabric():
    return filters.create(lambda _, __, message: (
        bool(message.from_user and (message.from_user.username or "").lower() == settings.superadmin_username.lower())
    ))

def in_channel_member_fabric(channel_id: int, require_username_match: bool = False) -> filters.Filter:
    async def predicate(_, client, message) -> bool:
        user = message.from_user
        if not user:
            return False  # нет данных о пользователе (например, service message)

        try:
            member = await client.get_chat_member(channel_id, user.id)
            # Если нужно только наличие — достаточно успешного возврата member
            if not require_username_match:
                return True

            # require_username_match == True: проверяем username
            # если username отсутствует в объекте member.user или в message.from_user -> False
            member_username = (member.user.username or "").lower()
            msg_username = (user.username or "").lower()
            if not bool(member_username) and member_username == msg_username:
                await client.send_message(user.id, "Пожалуйста, подпишитесь на наш канал чтобы продолжить",
                                          reply_markup=InlineKeyboardMarkup(
                                              [[InlineKeyboardButton("Подписаться", url="https://t.me/AuraScouting")]]))
                return False
            else:
                return True

        except UserNotParticipant:
            await client.send_message(user.id, "Пожалуйста, подпишитесь на наш канал чтобы продолжить", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Подписаться", url="https://t.me/AuraScouting")]]))
            return False
        except Forbidden as e:
            print(f"[in_channel_member_filter] bot has been not accessible for channel: {e}")
            await client.send_message(user.id, "Пожалуйста, подпишитесь на наш канал чтобы продолжить", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Подписаться", url="https://t.me/AuraScouting")]]))
            return False
        except FloodWait as e:
            print(f"[in_channel_member_filter] FloodWait {e.value} sec")
            await client.send_message(user.id, "Пожалуйста, подпишитесь на наш канал чтобы продолжить", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Подписаться", url="https://t.me/AuraScouting")]]))
            return False
        except Exception as e:
            print(f"[in_channel_member_filter] unexpected error: {e}")
            return False

    return filters.create(predicate)

allowed_superadmin_rule = superadmin_rule_fabric()
allowed_moder_rule = moder_rule_fabric()
allowed_admin_rule = admin_rule_fabric()
member_rule = in_channel_member_fabric(settings.channel_id, require_username_match=True)

