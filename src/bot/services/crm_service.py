import aiohttp
import asyncio
import re
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

async def _extract_csrf_from_json(resp: aiohttp.ClientResponse) -> Optional[str]:
    try:
        data = await resp.json()
        if isinstance(data, dict) and "csrfToken" in data:
            return data["csrfToken"]
    except Exception:
        return None
    return None

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
) -> aiohttp.ClientResponse:
    form = {
        "username": username,
        "password": password,
    }
    if extra_form:
        form.update(extra_form)

    if csrf_token:
        form[csrf_field_name] = csrf_token

    req_headers = headers.copy() if headers else {}
    if csrf_token:
        req_headers.setdefault("X-CSRFToken", csrf_token)
        req_headers.setdefault("X-XSRF-TOKEN", csrf_token)
    async with session.post(auth_url, data=form, headers=req_headers) as resp:
        await resp.text()
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
                    logger.info(f"post_json_with_auth: success post {status} with response {text}")
                    try:
                        return await resp.json()
                    except Exception:
                        return {"status": status, "text": text}
                if status == 401:
                    logger.warning(f"post_json_with_auth: fail post {status} with response {text}, try auth")
                    if not (csrf_url and auth_url and username and password):
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status,
                            message="401 received and auth parameters not provided"
                        )
                    csrf_token = await get_csrf_token(session, csrf_url)
                    auth_resp = await auth_with_csrf(session, auth_url, username, password, csrf_token=csrf_token)
                    logger.info(f"post_json_with_auth: success auth {auth_resp.status} with response {auth_resp.text()}, try auth")
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
