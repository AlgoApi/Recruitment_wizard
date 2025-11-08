import os
import logging
from pydantic_settings import BaseSettings

MAX_TRY_RECONNECT=3

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    bot_token: str
    api_id: int
    api_hash: str
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    superadmin_username: str = "algoapi"
    group_id: int
    help_group_id: int
    message_group_id: int
    partner_group_id: int
    agent_group_id: int
    channel_id: str

field_names = list(Settings.model_fields.keys())

kwargs = {}
for fname in field_names:
    val = os.getenv(fname.upper())
    if val is not None:
        kwargs[fname] = val
    else:
        logger.error(f"plz check our .env file: '{fname.upper()}' not found")

settings = Settings(**kwargs)

