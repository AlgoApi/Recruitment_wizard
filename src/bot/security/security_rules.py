from pyrogram import filters
from ..config import settings

MODER_USERNAMES = set()
ADMIN_USERNAMES = set()

def moder_rule_fabric():
    return filters.create(lambda _, __, message: (
        bool(message.from_user and (message.from_user.username or "").lower() in {u.lower() for u in list(MODER_USERNAMES)})
    ))

def admin_rule_fabric():
    return filters.create(lambda _, __, message: (
        bool(message.from_user and (message.from_user.username or "").lower() in {u.lower() for u in list(ADMIN_USERNAMES)})
    ))

def superadmin_rule_fabric():
    return filters.create(lambda _, __, message: (
        bool(message.from_user and (message.from_user.username or "").lower() == settings.superadmin_username.lower())
    ))

allowed_superadmin_rule = superadmin_rule_fabric()
allowed_moder_rule = moder_rule_fabric()
allowed_admin_rule = moder_rule_fabric()

