import aiohttp
from typing import Optional

_default_timeout = aiohttp.ClientTimeout(total=30)

class SessionManager:
    _session: Optional[aiohttp.ClientSession] = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            cls._session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), timeout=_default_timeout)
        cls._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            timeout=_default_timeout
        )
        return cls._session

    @classmethod
    async def close_session(cls) -> None:
        if cls._session is not None and not cls._session.closed:
            await cls._session.close()
            cls._session = None
