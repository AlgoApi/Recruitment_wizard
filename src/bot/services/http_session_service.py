import aiohttp
from typing import Optional, Dict

_default_timeout = aiohttp.ClientTimeout(total=30)

class SessionManager:
    _session: Optional[Dict[str, aiohttp.ClientSession]] = None

    @classmethod
    async def get_session(cls, target) -> aiohttp.ClientSession:
        if cls._session.get(target) is None or cls._session.get(target).closed:
            cls._session[target] = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                timeout=_default_timeout
            )
        return cls._session[target]

    @classmethod
    async def close_session(cls) -> None:
        if cls._session.get(target) is not None and not cls._session.get(target).closed:
            await cls._session.get(target).close()
            cls._session[target] = None
