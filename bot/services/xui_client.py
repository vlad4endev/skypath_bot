"""
3X-UI Panel API Client
"""
import uuid
import asyncio
import logging
import hashlib
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")
MAX_RETRIES = 3
RETRY_DELAY_SEC = 1.5


class XUIClient:
    def __init__(self, host: str, url_prefix: str, username: str, password: str):
        self.host = host.rstrip("/")
        self.prefix = url_prefix.rstrip("/")
        self.username = username
        self.password = password
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

    async def _get_cookie(self) -> str:
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
                cookies = resp.headers.get("set-cookie", "")
                self._cookie = cookies.split(";")[0] if cookies else ""
                self._cookie_expires = datetime.utcnow() + timedelta(hours=12)
                logger.info("3X-UI login successful")
                return self._cookie

        return await self._retry(_login, "login")

    def _gen_uuid(self) -> str:
        return str(uuid.uuid4())

    def _gen_email(self, first_name: str, last_name: str) -> str:
        clean = f"{first_name}{last_name}".lower()
        clean = "".join(c for c in clean if c.isalnum())
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{clean}_{suffix}"

    def _gen_sub_id(self) -> str:
        return hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:16]

    def _expiry_unix(self, months: int) -> int:
        expire_date = datetime.utcnow() + timedelta(days=30 * months)
        expire_date = expire_date.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(expire_date.timestamp() * 1000)

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
        cookie = await self._get_cookie()
        client_uuid = self._gen_uuid()
        email = self._gen_email(first_name, last_name)
        sub_id = self._gen_sub_id()
        expiry = self._expiry_unix(months)
        traffic_bytes = traffic_gb * 1024**3 if traffic_gb else 0

        payload = {
            "id": inbound_id,
            "settings": (
                f'{{"clients": [{{'
                f'"id": "{client_uuid}",'
                f'"flow": "",'
                f'"email": "{email}",'
                f'"limitIp": {limit_ip},'
                f'"totalGB": {traffic_bytes},'
                f'"expiryTime": {expiry},'
                f'"enable": true,'
                f'"tgId": "{telegram_id}",'
                f'"subId": "{sub_id}",'
                f'"reset": 0'
                f'}}]}}'
            ),
        }

        async def _add():
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.post(
                    f"{self._base_url()}/panel/api/inbounds/addClient",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Cookie": cookie,
                    },
                    json=payload,
                )
            data = resp.json() if resp.status_code == 200 else {}
            if not data.get("success", False):
                raise RuntimeError(data.get("msg", "addClient failed"))
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
        cookie = await self._get_cookie()
        expiry = self._expiry_unix(months)

        payload = {
            "id": inbound_id,
            "settings": (
                f'{{"clients": [{{'
                f'"id": "{client_uuid}",'
                f'"flow": "",'
                f'"email": "{email}",'
                f'"limitIp": {limit_ip},'
                f'"totalGB": 0,'
                f'"expiryTime": {expiry},'
                f'"enable": {"true" if enable else "false"},'
                f'"tgId": "{telegram_id}",'
                f'"subId": "{sub_id}",'
                f'"reset": 0'
                f'}}]}}'
            ),
        }

        async def _update():
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.post(
                    f"{self._base_url()}/panel/api/inbounds/updateClient/{client_uuid}",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Cookie": cookie,
                    },
                    json=payload,
                )
            data = resp.json() if resp.status_code == 200 else {}
            success = data.get("success", False)
            logger.info("%s updateClient %s: %s", "OK" if success else "FAIL", email, data.get("msg", ""))
            if not success:
                raise RuntimeError(data.get("msg", "updateClient failed"))
            return success

        return await self._retry(_update, "updateClient")

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        cookie = await self._get_cookie()

        async def _delete():
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                resp = await client.post(
                    f"{self._base_url()}/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
                    headers={"Cookie": cookie},
                )
            data = resp.json() if resp.status_code == 200 else {}
            if not data.get("success", False):
                raise RuntimeError(data.get("msg", "deleteClient failed"))
            return True

        return await self._retry(_delete, "deleteClient")

    async def disable_client(
        self, inbound_id: int, client_uuid: str,
        email: str, sub_id: str, telegram_id: int, limit_ip: int
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
        return f"{self.host}{self.prefix}/panel/api/client/sub/{sub_id}"

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

        tasks = [
            self.add_client(
                inbound_id=iid,
                first_name=first_name,
                last_name=last_name,
                telegram_id=telegram_id,
                months=months,
                limit_ip=limit_ip,
            )
            for iid in inbound_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info("Added to %s/%s inbounds", success_count, len(inbound_ids))

        first_success = next((r for r in results if not isinstance(r, Exception)), None)
        if not first_success:
            raise RuntimeError("Failed to add client to any inbound")

        return first_success
