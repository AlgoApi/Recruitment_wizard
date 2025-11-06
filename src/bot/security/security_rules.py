from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..config import settings
from pyrogram.errors import UserNotParticipant, FloodWait, Forbidden

MODER_USERNAMES = dict()
ADMIN_USERNAMES = dict()

async def send_subscribe_btn(client, user_id):
    await client.send_message(user_id, "Пожалуйста, подпишитесь на наш канал чтобы продолжить",
                              reply_markup=InlineKeyboardMarkup(
                                  [[InlineKeyboardButton("Подписаться", url="https://t.me/AuraScouting")],
                                   [InlineKeyboardButton("Я подписался!", callback_data="cmd_start_exec")]]))

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
            return False

        try:
            member = await client.get_chat_member(channel_id, user.id)
            if not require_username_match:
                return True

            member_username = (member.user.username or "").lower()
            msg_username = (user.username or "").lower()
            if not bool(member_username) and member_username == msg_username:
                await send_subscribe_btn(client, user.id)
                return False
            else:
                return True

        except UserNotParticipant:
            await send_subscribe_btn(client, user.id)
            return False
        except Forbidden as e:
            print(f"[in_channel_member_filter] bot has been not accessible for channel: {e}")
            await send_subscribe_btn(client, user.id)
            return False
        except FloodWait as e:
            print(f"[in_channel_member_filter] FloodWait {e.value} sec")
            await send_subscribe_btn(client, user.id)
            return False
        except Exception as e:
            print(f"[in_channel_member_filter] unexpected error: {e}")
            return False

    return filters.create(predicate)

def multiple_poller_guardian_fabric(log, session_store):
    @filters.create
    async def poller_guardian(_, client, message) -> bool:
        try:
            chat_id = message.chat.id
            msg_id = message.id
        except AttributeError:
            chat_id = message.message.chat.id
            msg_id = message.message.id
        key = f"processed:msg:{chat_id}:{msg_id}"
        ttl_seconds = 60 * 30

        got = await session_store.set_other(key, "1", nx=True, ex=ttl_seconds)
        if not got:
            log.debug("Skipping already-processed message %s:%s", chat_id, msg_id)
            return False
        log.info("Accepted message for processing %s:%s", chat_id, msg_id)
        return True

    return poller_guardian

allowed_superadmin_rule = superadmin_rule_fabric()
allowed_moder_rule = moder_rule_fabric()
allowed_admin_rule = admin_rule_fabric()
member_rule = in_channel_member_fabric(settings.channel_id, require_username_match=True)

