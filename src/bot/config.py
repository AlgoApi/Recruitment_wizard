import os
import logging
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    bot_token: str
    api_id: int
    api_hash: str
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    superadmin_username: str = "algoapi"
    admin_group_id: int

field_names = list(Settings.model_fields.keys())

kwargs = {}
for fname in field_names:
    val = os.getenv(fname.upper())
    if val is not None:
        kwargs[fname] = val
    else:
        logger.error(f"plz check our .env file: '{fname.upper()}' not found")

settings = Settings(**kwargs)

