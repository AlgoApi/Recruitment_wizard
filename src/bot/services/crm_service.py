import aiohttp
import asyncio
import re
from typing import Any, Dict, Optional
import logging
from yarl import URL

logger = logging.getLogger(__name__)

async def _extract_csrf_from_json(resp: aiohttp.ClientResponse) -> Optional[str]:
    try:
        data = await resp.json()
        if isinstance(data, dict) and "csrfToken" in data:
            return data["csrfToken"]
    except Exception:
        return None
    return None

def debug_print_response_cookies(resp):
    logger.info(f"post_json_with_auth: resp.status={resp.status}")
    logger.info(f"post_json_with_auth: Set-Cookie headers:{resp.headers.getall("Set-Cookie", [])}")
    for name, morsel in resp.cookies.items():
        logger.info(f"post_json_with_auth: resp.cookies:{name} {morsel.value} -> {dict(morsel)}")

def debug_print_session_cookies(session, url):
    jar = session.cookie_jar
    cookies = jar.filter_cookies(url)
    logger.info(f"post_json_with_auth: Session cookies for {url}")
    for name, cookie in cookies.items():
        logger.info(f"post_json_with_auth: {name} {cookie.value} domain: {cookie['domain']} path: {cookie['path']} secure: {cookie['secure']} httponly:{cookie['httponly']}")

async def get_csrf_token(session: aiohttp.ClientSession, csrf_url: str) -> Optional[str]:
    async with session.get(csrf_url) as resp:
        if resp.status != 200:
            text = await resp.text()
        else:
            token = await _extract_csrf_from_json(resp)
            if token:
                return token
            text = await resp.text()
    raise RuntimeError(f"Unable to obtain CSRF token from csrf_url: {text}")

async def auth_with_csrf(
    session: aiohttp.ClientSession,
    auth_url: str,
    username: str,
    password: str,
    csrf_token: Optional[str] = None,
    csrf_field_name: str = "csrfToken",
    extra_form: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
    base_url: str = "https://huntmecrm.com",
) -> aiohttp.ClientResponse:
    req_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Origin": "https://huntmecrm.com",
        "Referer": "https://huntmecrm.com/login",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        all_cookies = session.cookie_jar.filter_cookies(URL(auth_url))
        if all_cookies:
            cookie_header_str = "; ".join([f"{k}={v.value}" for k, v in all_cookies.items()])
            req_headers["Cookie"] = cookie_header_str
            logger.info(f"auth_with_csrf: Manually forcing Cookie header: {cookie_header_str}")
        else:
            logger.warning("auth_with_csrf: No cookies found in jar to force!")
    except Exception as e:
        logger.error(f"auth_with_csrf: Error forming cookie header: {e}")

    form = {
        "username": username,
        "password": password,
        "callbackUrl": "https://huntmecrm.com/login",
        "redirect": "false",
        "csrfToken": csrf_token,
        "json": "true"
    }

    if headers:
        req_headers.update(headers)
    if extra_form:
        form.update(extra_form)

    logger.info(f"auth_with_csrf: sending POST to {auth_url} with headers {req_headers} with form {form}")
    async with session.post(auth_url, data=form, headers=req_headers, allow_redirects=False) as resp:
        recive = await resp.text()
        logger.info(f"auth_with_csrf {recive} and {resp.status}")
        session_cookies = [name for name, _ in resp.cookies.items()]
        logger.info(f"auth_with_csrf received cookies: {session_cookies}")
        set_cookie = resp.headers.getall("Set-Cookie", [])
        logger.info(f"Auth response headers Set-Cookie: {set_cookie}")
        cookies = session.cookie_jar.filter_cookies(auth_url)
        for cookie_str in set_cookie:
            if "session-token" in cookie_str:
                session.cookie_jar.update_cookies(resp.cookies, response_url=URL(auth_url))
                logger.info("Session token manually updated in Jar")
        has_session = any("session-token" in name for name in cookies.keys())

        if not has_session:
            if resp.status == 302 or resp.status == 303:
                location = resp.headers.get('Location', '')
                if 'error' in location:
                    logger.error(f"auth_with_csrf: Login FAILED. Redirected to error: {location}")
                else:
                    logger.warning(f"auth_with_csrf: Redirected to {location} but no session cookie found.")
            elif resp.status == 401:
                logger.error("auth_with_csrf: 401 Unauthorized (Credentials incorrect?)")
            else:
                logger.error(f"auth_with_csrf: Unexpected status {resp.status}. Response: {text[:200]}")
        else:
            logger.info("auth success")
            session.cookie_jar.update_cookies(resp.cookies, response_url=URL(auth_url))

        return resp

async def post_json_with_auth(
    session: aiohttp.ClientSession,
    api_url: str,
    payload: Dict[str, Any],
    *,
    csrf_url: Optional[str] = None,
    auth_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    max_attempts: int = 2
) -> Dict[str, Any]:
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < max_attempts:
        attempt += 1
        try:
            logger.info(f"post_json_with_auth: try post {api_url} payload {payload}")
            async with session.post(api_url, json=payload, headers={"Accept":"application/json"}) as resp:
                status = resp.status
                text = await resp.text()
                if 200 <= status < 300:
                    logger.info(f"post_json_with_auth: success post {status} with response {text[:20]}")
                    try:
                        return await resp.json()
                    except Exception:
                        return {"status": status, "text": text}
                if status == 401:
                    logger.warning(f"post_json_with_auth: fail post {status} with response {text[:20]}, try auth")
                    if not (csrf_url and auth_url and username and password):
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status,
                            message="401 received and auth parameters not provided"
                        )
                    csrf_token = await get_csrf_token(session, csrf_url)
                    auth_resp = await auth_with_csrf(session, auth_url, username, password, csrf_token=csrf_token)
                    auth_resp_text = await auth_resp.text()
                    logger.info(f"post_json_with_auth: success auth {auth_resp.status} with response {auth_resp_text[:20]}")
                    debug_print_session_cookies(session, api_url)
                    if auth_resp.status >= 400:
                        last_exc = aiohttp.ClientResponseError(
                            auth_resp.request_info, auth_resp.history, status=auth_resp.status,
                            message=f"auth failed: {await auth_resp.text()}"
                        )
                        continue
                    continue
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status, message=text)
        except Exception as e:
            last_exc = e
            await asyncio.sleep(0.2)
            continue

    # exhausted attempts
    raise last_exc or RuntimeError("post_json_with_auth failed without an exception")
