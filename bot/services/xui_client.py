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
        sub_base_url: str = "",
    ):
        self.host = host.rstrip("/")
        self.prefix = url_prefix.rstrip("/")
        self.username = username
        self.password = password
        self.api_token = api_token.strip()
        self.sub_path = sub_path if sub_path.endswith("/") else f"{sub_path}/"
        self.sub_base_url = sub_base_url.strip().rstrip("/")
        self._cookie: Optional[str] = None
        self._cookie_expires: Optional[datetime] = None
        self._inbound_cache: dict[int, dict[str, Any]] | None = None
        self._inbound_cache_at: Optional[datetime] = None

    def _base_url(self) -> str:
        return f"{self.host}{self.prefix}"

    def _parse_response(self, resp: httpx.Response, label: str) -> dict[str, Any]:
        if not resp.content:
            return {}

        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError(
                f"{label}: invalid JSON (HTTP {resp.status_code}): {resp.text[:300]}"
            ) from e

        if not isinstance(data, dict):
            raise RuntimeError(f"{label}: unexpected response type (HTTP {resp.status_code})")

        if resp.status_code >= 400 or data.get("success") is False:
            raise RuntimeError(data.get("msg", f"{label} HTTP {resp.status_code}"))

        return data

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

        async def _login_once(use_form: bool) -> str:
            url = f"{self._base_url()}/login"
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                if use_form:
                    resp = await client.post(
                        url,
                        data={"username": self.username, "password": self.password},
                    )
                else:
                    resp = await client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={"username": self.username, "password": self.password},
                    )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("success", False):
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
                logger.info("3X-UI login successful (%s)", "form" if use_form else "json")
                return self._cookie

        async def _login():
            last_error: Exception | None = None
            for use_form in (False, True):
                try:
                    return await _login_once(use_form)
                except Exception as e:
                    last_error = e
                    logger.warning("3X-UI login %s failed: %s", "form" if use_form else "json", e)
            raise RuntimeError(f"3X-UI login failed: {last_error}") from last_error

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

            return self._parse_response(resp, label)

        return await self._retry(_call, label)

    async def _post_raw(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        label: str,
    ) -> dict[str, Any]:
        cookie = await self._get_cookie()
        url = f"{self._base_url()}{path}"
        async with httpx.AsyncClient(verify=False, timeout=20) as client:
            resp = await client.post(
                url,
                headers=self._auth_headers(cookie),
                json=payload,
            )
        if not resp.content:
            logger.warning("%s: empty body (HTTP %s)", label, resp.status_code)
            return {}
        return self._parse_response(resp, label)

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

    def _expiry_unix_days(self, days: int) -> int:
        expire_date = datetime.utcnow() + timedelta(days=days)
        expire_date = expire_date.replace(hour=23, minute=59, second=59, microsecond=0)
        return int(expire_date.timestamp() * 1000)

    def _expiry_unix_from_datetime(self, dt: datetime) -> int:
        expire_date = dt.replace(hour=23, minute=59, second=59, microsecond=0)
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
        flow: str = "",
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
            "tgId": int(telegram_id),
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

    async def get_client_traffic(self, email: str) -> dict[str, Any] | None:
        """Трафик клиента из 3X-UI: up/down в байтах, лимит, безлимит."""
        try:
            raw = await self.get_client(email)
        except Exception as e:
            logger.warning("get_client_traffic failed for %s: %s", email, e)
            return None

        client = raw
        if isinstance(raw, dict) and "clients" in raw:
            clients = raw.get("clients") or []
            client = clients[0] if clients else raw

        if not isinstance(client, dict):
            return None

        up = int(client.get("up") or 0)
        down = int(client.get("down") or 0)
        used_bytes = up + down
        limit_bytes = int(client.get("totalGB") or 0)
        unlimited = limit_bytes <= 0
        limit_gb = round(limit_bytes / (1024**3), 2) if limit_bytes > 0 else 0
        used_gb = round(used_bytes / (1024**3), 2)

        pct = 0.0
        if not unlimited and limit_bytes > 0:
            pct = min(100.0, round(used_bytes / limit_bytes * 100, 1))

        return {
            "up_bytes": up,
            "down_bytes": down,
            "used_bytes": used_bytes,
            "used_gb": used_gb,
            "limit_bytes": limit_bytes,
            "limit_gb": limit_gb,
            "unlimited": unlimited,
            "usage_percent": pct,
            "enabled": bool(client.get("enable", True)),
        }

    def _parse_inbound_clients(self, inbound: dict[str, Any]) -> list[dict[str, Any]]:
        inbound_id = int(inbound.get("id") or 0)
        clients: list[dict[str, Any]] = []

        settings_raw = inbound.get("settings")
        if isinstance(settings_raw, str) and settings_raw.strip():
            try:
                settings = json.loads(settings_raw)
            except json.JSONDecodeError:
                settings = {}
        elif isinstance(settings_raw, dict):
            settings = settings_raw
        else:
            settings = {}

        for client in settings.get("clients") or []:
            if isinstance(client, dict) and client.get("email"):
                clients.append({**client, "_inbound_id": inbound_id})

        for stat in inbound.get("clientStats") or []:
            if not isinstance(stat, dict):
                continue
            email = stat.get("email")
            if not email:
                continue
            if any(c.get("email") == email for c in clients):
                continue
            clients.append({**stat, "_inbound_id": inbound_id})

        return clients

    async def list_all_clients(self) -> list[dict[str, Any]]:
        """Все VPN-клиенты из inbounds (для массовой синхронизации)."""
        inbounds = await self.list_inbounds()
        result: list[dict[str, Any]] = []
        for inbound in inbounds:
            result.extend(self._parse_inbound_clients(inbound))
        return result

    async def build_client_index(self) -> dict[str, dict[str, Any]]:
        """Индекс клиентов панели по email / subId / tgId / uuid."""
        by_email: dict[str, dict[str, Any]] = {}
        by_sub_id: dict[str, dict[str, Any]] = {}
        by_tg_id: dict[int, dict[str, Any]] = {}
        by_uuid: dict[str, dict[str, Any]] = {}

        for client in await self.list_all_clients():
            email = str(client.get("email") or "").strip()
            if email and email not in by_email:
                by_email[email] = client

            sub_id = str(client.get("subId") or "").strip()
            if sub_id and sub_id not in by_sub_id:
                by_sub_id[sub_id] = client

            tg_raw = client.get("tgId")
            if tg_raw is not None and str(tg_raw).strip() != "":
                try:
                    tg_id = int(tg_raw)
                except (TypeError, ValueError):
                    tg_id = 0
                if tg_id > 0 and tg_id not in by_tg_id:
                    by_tg_id[tg_id] = client

            client_uuid = str(client.get("id") or "").strip()
            if client_uuid and client_uuid not in by_uuid:
                by_uuid[client_uuid] = client

        return {
            "by_email": by_email,
            "by_sub_id": by_sub_id,
            "by_tg_id": by_tg_id,
            "by_uuid": by_uuid,
        }

    async def find_panel_client(
        self,
        index: dict[str, dict[str, dict[str, Any]]],
        *,
        email: str | None = None,
        sub_id: str | None = None,
        telegram_id: int | None = None,
        client_uuid: str | None = None,
    ) -> dict[str, Any] | None:
        """Найти клиента в предзагруженном индексе, при email — уточнить через API."""
        match: dict[str, Any] | None = None

        if email:
            match = index["by_email"].get(email.strip())
        if match is None and sub_id:
            match = index["by_sub_id"].get(sub_id.strip())
        if match is None and telegram_id:
            match = index["by_tg_id"].get(int(telegram_id))
        if match is None and client_uuid:
            match = index["by_uuid"].get(client_uuid.strip())

        if match is None:
            return None

        client_email = str(match.get("email") or "").strip()
        if not client_email:
            return match

        try:
            fresh = await self.get_client(client_email)
        except Exception as e:
            logger.warning("find_panel_client: get_client(%s) failed: %s", client_email, e)
            return match

        if isinstance(fresh, dict) and "clients" in fresh:
            clients = fresh.get("clients") or []
            if clients and isinstance(clients[0], dict):
                merged = {**clients[0], "_inbound_id": match.get("_inbound_id")}
                return merged
        if isinstance(fresh, dict):
            return {**fresh, "_inbound_id": match.get("_inbound_id")}
        return match

    async def get_servers_status(self, inbound_ids: dict[str, int]) -> list[dict[str, Any]]:
        """Статус серверов по inbound ID из панели."""
        try:
            inbounds = await self.list_inbounds()
        except Exception as e:
            logger.warning("get_servers_status failed: %s", e)
            return [
                {"name": name, "online": None}
                for name in inbound_ids
            ]

        by_id = {int(ib.get("id", 0)): ib for ib in inbounds if ib.get("id") is not None}
        result = []
        for name, iid in inbound_ids.items():
            ib = by_id.get(int(iid))
            if ib is None:
                result.append({"name": name, "online": None})
            else:
                result.append({
                    "name": name,
                    "online": bool(ib.get("enable", False)),
                })
        return result

    async def _get_inbound(self, inbound_id: int) -> dict[str, Any] | None:
        now = datetime.utcnow()
        if (
            self._inbound_cache is not None
            and self._inbound_cache_at
            and now - self._inbound_cache_at < timedelta(minutes=5)
        ):
            return self._inbound_cache.get(inbound_id)

        inbounds = await self.list_inbounds()
        self._inbound_cache = {
            int(ib["id"]): ib for ib in inbounds if ib.get("id") is not None
        }
        self._inbound_cache_at = now
        return self._inbound_cache.get(inbound_id)

    def _flow_for_inbound(self, inbound: dict[str, Any] | None) -> str:
        if not inbound or inbound.get("protocol") != "vless":
            return ""
        stream = inbound.get("streamSettings") or {}
        if isinstance(stream, str):
            try:
                stream = json.loads(stream)
            except json.JSONDecodeError:
                return ""
        security = stream.get("security", "")
        network = stream.get("network", "tcp")
        if security in ("tls", "reality") and network == "tcp":
            return "xtls-rprx-vision"
        return ""

    def _client_for_settings(self, client: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in client.items() if k != "inboundIds"}

    async def _verify_client_exists(self, email: str) -> bool:
        try:
            await self.get_client(email)
            return True
        except Exception:
            return False

    async def _add_client_legacy(
        self,
        inbound_id: int,
        client: dict[str, Any],
    ) -> None:
        settings_client = self._client_for_settings(client)
        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [settings_client]}, separators=(",", ":")),
        }
        await self._post_raw(
            "/panel/api/inbounds/addClient",
            payload,
            label="legacy addClient",
        )

    async def _add_client_inbounds(
        self,
        inbound_ids: list[int],
        client: dict[str, Any],
    ) -> None:
        settings_client = self._client_for_settings(client)
        payload = {
            "inboundIds": inbound_ids,
            "settings": json.dumps({"clients": [settings_client]}, separators=(",", ":")),
        }
        await self._post_raw(
            "/panel/api/inbounds/addClientInbounds",
            payload,
            label="addClientInbounds",
        )

    async def _create_client_on_panel(
        self,
        inbound_id: int,
        client: dict[str, Any],
        email: str,
    ) -> None:
        errors: list[str] = []
        attempts: list[tuple[str, Callable[[], Awaitable[None]]]] = [
            (
                "clients/add",
                lambda: self._request(
                    "POST",
                    "/panel/api/clients/add",
                    json_body={
                        "client": self._client_for_settings(client),
                        "inboundIds": [inbound_id],
                    },
                    label="clients/add",
                ),
            ),
            (
                "addClientInbounds",
                lambda: self._add_client_inbounds([inbound_id], client),
            ),
            (
                "addClient",
                lambda: self._add_client_legacy(inbound_id, client),
            ),
        ]

        for name, fn in attempts:
            try:
                await fn()
                if await self._verify_client_exists(email):
                    logger.info("3X-UI client %s created via %s", email, name)
                    return
                errors.append(f"{name}: panel accepted request but client not found")
            except Exception as e:
                errors.append(f"{name}: {e}")

        raise RuntimeError("; ".join(errors))

    async def add_client(
        self,
        inbound_id: int,
        first_name: str,
        last_name: str,
        telegram_id: int,
        months: int,
        limit_ip: int = 3,
        traffic_gb: int = 0,
        days: int = 0,
    ) -> dict:
        client_uuid = self._gen_uuid()
        email = self._gen_email(first_name, last_name)
        sub_id = self._gen_sub_id()
        expiry = self._expiry_unix_days(days) if days > 0 else self._expiry_unix(months)
        traffic_bytes = traffic_gb * 1024**3 if traffic_gb else 0

        inbound = await self._get_inbound(inbound_id)
        if inbound is None:
            logger.warning("Inbound %s not found in panel, using configured id anyway", inbound_id)

        client = self._build_client_payload(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            telegram_id=telegram_id,
            expiry=expiry,
            traffic_bytes=traffic_bytes,
            limit_ip=limit_ip,
            enable=True,
            flow=self._flow_for_inbound(inbound),
        )

        async def _add():
            await self._create_client_on_panel(inbound_id, client, email)
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
        limit_ip: int,
        *,
        months: int = 0,
        expiry_unix: int | None = None,
        enable: bool = True,
        traffic_gb: int = 0,
    ) -> bool:
        if expiry_unix is None:
            expiry_unix = self._expiry_unix(months)
        traffic_bytes = int(traffic_gb * (1024 ** 3)) if traffic_gb > 0 else 0
        client = self._build_client_payload(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            telegram_id=telegram_id,
            expiry=expiry_unix,
            traffic_bytes=traffic_bytes,
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
            limit_ip=limit_ip,
            months=0,
            enable=False,
        )

    def build_sub_url(self, sub_id: str) -> str:
        if self.sub_base_url:
            return f"{self.sub_base_url}/{sub_id}"
        return f"{self.host}{self.sub_path}{sub_id}"

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
        inbound = await self._get_inbound(inbound_ids[0]) if inbound_ids else None
        client = self._build_client_payload(
            client_uuid=client_uuid,
            email=email,
            sub_id=sub_id,
            telegram_id=telegram_id,
            expiry=expiry,
            traffic_bytes=0,
            limit_ip=limit_ip,
            enable=True,
            flow=self._flow_for_inbound(inbound),
        )

        async def _bulk_add():
            errors: list[str] = []
            try:
                await self._request(
                    "POST",
                    "/panel/api/clients/add",
                    json_body={"client": self._client_for_settings(client), "inboundIds": inbound_ids},
                    label="clients/add (multi)",
                )
                if await self._verify_client_exists(email):
                    logger.info("Added client %s to %s inbounds", email, len(inbound_ids))
                    return {
                        "uuid": client_uuid,
                        "email": email,
                        "sub_id": sub_id,
                        "expiry_unix": expiry,
                    }
                errors.append("clients/add: client not found after OK response")
            except Exception as e:
                errors.append(f"clients/add: {e}")

            try:
                await self._add_client_inbounds(inbound_ids, client)
                if await self._verify_client_exists(email):
                    logger.info("Added client %s via addClientInbounds", email)
                    return {
                        "uuid": client_uuid,
                        "email": email,
                        "sub_id": sub_id,
                        "expiry_unix": expiry,
                    }
                errors.append("addClientInbounds: client not found after OK response")
            except Exception as e:
                errors.append(f"addClientInbounds: {e}")

            for iid in inbound_ids:
                try:
                    await self._create_client_on_panel(iid, client, email)
                    if await self._verify_client_exists(email):
                        return {
                            "uuid": client_uuid,
                            "email": email,
                            "sub_id": sub_id,
                            "expiry_unix": expiry,
                        }
                except Exception as e:
                    errors.append(f"inbound {iid}: {e}")

            raise RuntimeError("; ".join(errors))

        return await self._retry(_bulk_add, "addToAllInbounds")
