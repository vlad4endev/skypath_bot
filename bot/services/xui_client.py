"""
3X-UI Panel API Client (v2+ clients API + Bearer token)
"""
import json
import uuid
import asyncio
import logging
import hashlib
import random
import string
from datetime import datetime, timedelta
from typing import Any, Optional, Callable, Awaitable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")
MAX_RETRIES = 3
RETRY_DELAY_SEC = 1.5


class XUIClient:
    def __init__(
        self,
        host: str,
        url_prefix: str,
        username: str,
        password: str,
        api_token: str = "",
        sub_path: str = "/sub/",
    ):
        self.host = host.rstrip("/")
        self.prefix = url_prefix.rstrip("/")
        self.username = username
        self.password = password
        self.api_token = api_token.strip()
        self.sub_path = sub_path if sub_path.endswith("/") else f"{sub_path}/"
        self._cookie: Optional[str] = None
        self._cookie_expires: Optional[datetime] = None

    def _base_url(self) -> str:
        return f"{self.host}{self.prefix}"

    async def _retry(self, operation: Callable[[], Awaitable[T]], label: str) -> T:
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await operation()
            except Exception as e:
                last_error = e
                logger.warning(
                    "3X-UI %s attempt %s/%s failed: %s",
                    label,
                    attempt,
                    MAX_RETRIES,
                    e,
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY_SEC * attempt)
        raise RuntimeError(f"3X-UI {label} failed after {MAX_RETRIES} attempts") from last_error

    def _auth_headers(self, cookie: str = "") -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        elif cookie:
            headers["Cookie"] = cookie
        return headers

    async def _get_cookie(self) -> str:
        if self.api_token:
            return ""

        if self._cookie and self._cookie_expires and datetime.utcnow() < self._cookie_expires:
            return self._cookie

        async def _login():
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.post(
                    f"{self._base_url()}/login",
                    headers={"Content-Type": "application/json"},
                    json={"username": self.username, "password": self.password},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("success", True):
                    raise RuntimeError(data.get("msg", "login failed"))

                if resp.cookies:
                    self._cookie = "; ".join(
                        f"{name}={value}" for name, value in resp.cookies.items()
                    )
                else:
                    raw = resp.headers.get("set-cookie", "")
                    self._cookie = raw.split(";")[0] if raw else ""

                if not self._cookie:
                    raise RuntimeError("3X-UI login: empty session cookie")

                self._cookie_expires = datetime.utcnow() + timedelta(hours=12)
                logger.info("3X-UI login successful")
                return self._cookie

        return await self._retry(_login, "login")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | list | None = None,
        label: str = "request",
    ) -> dict[str, Any]:
        cookie = await self._get_cookie()
        url = f"{self._base_url()}{path}"

        async def _call() -> dict[str, Any]:
            async with httpx.AsyncClient(verify=False, timeout=20) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=self._auth_headers(cookie),
                    json=json_body,
                )

            if not resp.content:
                raise RuntimeError(f"{label}: empty response (HTTP {resp.status_code})")

            try:
                data = resp.json()
            except ValueError as e:
                raise RuntimeError(
                    f"{label}: invalid JSON (HTTP {resp.status_code}): {resp.text[:200]}"
                ) from e

            if resp.status_code >= 400 or not data.get("success", False):
                raise RuntimeError(data.get("msg", f"{label} HTTP {resp.status_code}"))

            return data

        return await self._retry(_call, label)

    def _gen_uuid(self) -> str:
        return str(uuid.uuid4())

    def _gen_email(self, first_name: str, last_name: str) -> str:
        clean = f"{first_name}{last_name}".lower()
        clean = "".join(c for c in clean if c.isalnum())
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{clean or 'user'}_{suffix}"

    def _gen_sub_id(self) -> str:
        return hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:16]

    def _expiry_unix(self, months: int) -> int:
        expire_date = datetime.utcnow() + timedelta(days=30 * months)
        expire_date = expire_date.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(expire_date.timestamp() * 1000)

    def _build_client_payload(
        self,
        *,
        client_uuid: str,
        email: str,
        sub_id: str,
        telegram_id: int,
        expiry: int,
        traffic_bytes: int,
        limit_ip: int,
        enable: bool,
        flow: str = "xtls-rprx-vision",
    ) -> dict[str, Any]:
        return {
            "id": client_uuid,
            "email": email,
            "subId": sub_id,
            "flow": flow,
            "limitIp": limit_ip,
            "totalGB": traffic_bytes,
            "expiryTime": expiry,
            "enable": enable,
            "tgId": str(telegram_id),
            "reset": 0,
        }

    async def get_server_status(self) -> dict[str, Any]:
        """GET /panel/api/server/status — CPU, RAM, Xray state."""
        cookie = await self._get_cookie()
        url = f"{self._base_url()}/panel/api/server/status"

        async def _fetch():
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.get(url, headers=self._auth_headers(cookie))
            if resp.status_code >= 400:
                raise RuntimeError(f"server/status HTTP {resp.status_code}")
            data = resp.json()
            if isinstance(data, dict) and "success" in data and not data.get("success"):
                raise RuntimeError(data.get("msg", "server/status failed"))
            return data.get("obj", data) if isinstance(data, dict) else data

        return await self._retry(_fetch, "server/status")

    async def list_inbounds(self) -> list[dict[str, Any]]:
        """GET /panel/api/inbounds/list"""
        cookie = await self._get_cookie()
        url = f"{self._base_url()}/panel/api/inbounds/list"

        async def _fetch():
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.get(url, headers=self._auth_headers(cookie))
            data = resp.json()
            if resp.status_code >= 400 or not data.get("success", False):
                raise RuntimeError(data.get("msg", f"inbounds/list HTTP {resp.status_code}"))
            obj = data.get("obj", [])
            return obj if isinstance(obj, list) else []

        return await self._retry(_fetch, "inbounds/list")

    async def get_client(self, email: str) -> dict[str, Any]:
        """GET /panel/api/clients/get/{email}"""
        cookie = await self._get_cookie()
        url = f"{self._base_url()}/panel/api/clients/get/{email}"

        async def _fetch():
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.get(url, headers=self._auth_headers(cookie))
            data = resp.json()
            if resp.status_code >= 400 or not data.get("success", False):
                raise RuntimeError(data.get("msg", f"clients/get HTTP {resp.status_code}"))
            return data.get("obj", data)

        return await self._retry(_fetch, "clients/get")

    async def _add_client_legacy(
        self,
        inbound_id: int,
        client: dict[str, Any],
        cookie: str,
    ) -> None:
        payload = {
            "id": inbound_id,
            "settings": (
                '{"clients":['
                + json.dumps(client, separators=(",", ":"))
                + "]}"
            ),
        }
        url = f"{self._base_url()}/panel/api/inbounds/addClient"
        async with httpx.AsyncClient(verify=False, timeout=20) as http:
            resp = await http.post(
                url,
                headers=self._auth_headers(cookie),
                json=payload,
            )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or not data.get("success", False):
            raise RuntimeError(data.get("msg", f"legacy addClient HTTP {resp.status_code}"))

    async def add_client(
        self,
        inbound_id: int,
        first_name: str,
        last_name: str,
        telegram_id: int,
        months: int,
        limit_ip: int = 3,
        traffic_gb: int = 0,
    ) -> dict:
        client_uuid = self._gen_uuid()
        email = self._gen_email(first_name, last_name)
        sub_id = self._gen_sub_id()
        expiry = self._expiry_unix(months)
        traffic_bytes = traffic_gb * 1024**3 if traffic_gb else 0

        client = self._build_client_payload(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            telegram_id=telegram_id,
            expiry=expiry,
            traffic_bytes=traffic_bytes,
            limit_ip=limit_ip,
            enable=True,
        )

        async def _add():
            try:
                await self._request(
                    "POST",
                    "/panel/api/clients/add",
                    json_body={"client": client, "inboundIds": [inbound_id]},
                    label="clients/add",
                )
            except Exception as e:
                logger.warning("clients/add failed, trying legacy addClient: %s", e)
                cookie = await self._get_cookie()
                await self._add_client_legacy(inbound_id, client, cookie)

            logger.info("VPN client created: %s / inbound %s", email, inbound_id)
            return {
                "uuid": client_uuid,
                "email": email,
                "sub_id": sub_id,
                "expiry_unix": expiry,
            }

        return await self._retry(_add, "addClient")

    async def update_client(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str,
        sub_id: str,
        telegram_id: int,
        months: int,
        limit_ip: int,
        enable: bool = True,
    ) -> bool:
        expiry = self._expiry_unix(months)
        client = self._build_client_payload(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            telegram_id=telegram_id,
            expiry=expiry,
            traffic_bytes=0,
            limit_ip=limit_ip,
            enable=enable,
        )
        client["inboundIds"] = [inbound_id]

        async def _update():
            try:
                await self._request(
                    "POST",
                    f"/panel/api/clients/update/{email}",
                    json_body=client,
                    label="clients/update",
                )
            except Exception as e:
                logger.warning("clients/update failed, trying legacy updateClient: %s", e)
                cookie = await self._get_cookie()
                payload = {
                    "id": inbound_id,
                    "settings": (
                        '{"clients":['
                        + json.dumps(client, separators=(",", ":"))
                        + "]}"
                    ),
                }
                url = f"{self._base_url()}/panel/api/inbounds/updateClient/{client_uuid}"
                async with httpx.AsyncClient(verify=False, timeout=20) as http:
                    resp = await http.post(
                        url,
                        headers=self._auth_headers(cookie),
                        json=payload,
                    )
                data = resp.json() if resp.content else {}
                if not data.get("success", False):
                    raise RuntimeError(data.get("msg", "legacy updateClient failed"))

            logger.info("%s updateClient %s", "OK" if enable else "DISABLED", email)
            return True

        return await self._retry(_update, "updateClient")

    async def delete_client(self, inbound_id: int, client_uuid: str, email: str = "") -> bool:
        async def _delete():
            if email:
                try:
                    await self._request(
                        "POST",
                        f"/panel/api/clients/del/{email}",
                        label="clients/del",
                    )
                    return True
                except Exception as e:
                    logger.warning("clients/del failed, trying legacy delClient: %s", e)

            cookie = await self._get_cookie()
            url = f"{self._base_url()}/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
            async with httpx.AsyncClient(verify=False, timeout=15) as http:
                resp = await http.post(url, headers=self._auth_headers(cookie))
            data = resp.json() if resp.content else {}
            if not data.get("success", False):
                raise RuntimeError(data.get("msg", "deleteClient failed"))
            return True

        return await self._retry(_delete, "deleteClient")

    async def disable_client(
        self,
        inbound_id: int,
        client_uuid: str,
        email: str,
        sub_id: str,
        telegram_id: int,
        limit_ip: int,
    ) -> bool:
        return await self.update_client(
            inbound_id=inbound_id,
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            telegram_id=telegram_id,
            months=0,
            limit_ip=limit_ip,
            enable=False,
        )

    def build_sub_url(self, sub_id: str) -> str:
        return f"{self.host}{self.prefix}{self.sub_path}{sub_id}"

    async def add_to_all_inbounds(
        self,
        inbound_ids: list[int],
        first_name: str,
        last_name: str,
        telegram_id: int,
        months: int,
        limit_ip: int,
    ) -> dict:
        client_uuid = self._gen_uuid()
        email = self._gen_email(first_name, last_name)
        sub_id = self._gen_sub_id()
        expiry = self._expiry_unix(months)

        client = self._build_client_payload(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            telegram_id=telegram_id,
            expiry=expiry,
            traffic_bytes=0,
            limit_ip=limit_ip,
            enable=True,
        )

        async def _bulk_add():
            try:
                await self._request(
                    "POST",
                    "/panel/api/clients/add",
                    json_body={"client": client, "inboundIds": inbound_ids},
                    label="clients/add (multi)",
                )
            except Exception as e:
                logger.warning("bulk clients/add failed, adding per-inbound: %s", e)
                for iid in inbound_ids:
                    await self.add_client(
                        inbound_id=iid,
                        first_name=first_name,
                        last_name=last_name,
                        telegram_id=telegram_id,
                        months=months,
                        limit_ip=limit_ip,
                    )
                return {
                    "uuid": client_uuid,
                    "email": email,
                    "sub_id": sub_id,
                    "expiry_unix": expiry,
                }

            logger.info("Added client %s to %s inbounds", email, len(inbound_ids))
            return {
                "uuid": client_uuid,
                "email": email,
                "sub_id": sub_id,
                "expiry_unix": expiry,
            }

        return await self._retry(_bulk_add, "addToAllInbounds")
