"""
Клиент NocoDB API для wiki.skypath.fun и аналогичных инстансов.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class NocoDBClient:
    def __init__(self, base_url: str, token: str, base_id: str):
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.base_id = base_id.strip()
        self._headers = {"xc-token": self.token, "Accept": "application/json"}

    async def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url, headers=self._headers, params=params or {})
        if resp.status_code == 401:
            raise PermissionError("NocoDB: неверный API token (401)")
        resp.raise_for_status()
        return resp.json()

    async def list_tables_v2(self) -> list[dict[str, Any]]:
        data = await self._get(f"/api/v2/meta/bases/{self.base_id}/tables")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "list" in data:
            return data["list"]
        return []

    async def list_tables_v1(self) -> list[dict[str, Any]]:
        data = await self._get(f"/api/v1/db/meta/projects/{self.base_id}/tables")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "list" in data:
            return data["list"]
        return []

    async def list_tables(self) -> list[dict[str, Any]]:
        try:
            tables = await self.list_tables_v2()
            if tables:
                return tables
        except httpx.HTTPStatusError as e:
            logger.warning("NocoDB v2 meta failed: %s", e)
        return await self.list_tables_v1()

    async def fetch_records_v2(self, table_id: str, *, limit: int = 1000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            data = await self._get(
                f"/api/v2/tables/{table_id}/records",
                params={"limit": limit, "offset": offset},
            )
            batch = data.get("list", []) if isinstance(data, dict) else []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return rows

    async def fetch_records_v1(self, table_name: str, *, limit: int = 1000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            data = await self._get(
                f"/api/v1/db/data/noco/{self.base_id}/{table_name}",
                params={"limit": limit, "offset": offset},
            )
            batch = data.get("list", []) if isinstance(data, dict) else []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return rows

    async def fetch_table(self, table: dict[str, Any]) -> list[dict[str, Any]]:
        table_id = table.get("id") or table.get("table_id")
        title = table.get("title") or table.get("table_name") or table.get("name")
        if table_id:
            try:
                return await self.fetch_records_v2(str(table_id))
            except httpx.HTTPStatusError:
                pass
        if title:
            return await self.fetch_records_v1(str(title))
        raise ValueError(f"Cannot fetch table: {table}")


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """NocoDB v2 оборачивает поля в {field: value}; разворачиваем."""
    if not row:
        return row
    if any(isinstance(v, dict) and "value" in v for v in row.values()):
        flat: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, dict) and "value" in v:
                flat[k] = v["value"]
            else:
                flat[k] = v
        return flat
    return row


def guess_table(tables: list[dict[str, Any]], *keywords: str) -> dict[str, Any] | None:
    for table in tables:
        title = str(
            table.get("title") or table.get("table_name") or table.get("name") or ""
        ).lower()
        if any(kw in title for kw in keywords):
            return table
    return None


async def discover_schema(client: NocoDBClient) -> None:
    tables = await client.list_tables()
    print(f"Base: {client.base_id}")
    print(f"Tables: {len(tables)}\n")
    for t in tables:
        title = t.get("title") or t.get("table_name") or t.get("name")
        tid = t.get("id") or t.get("table_id")
        cols = t.get("columns") or []
        print(f"## {title} (id={tid})")
        if cols:
            for c in cols:
                ctitle = c.get("title") or c.get("column_name") or c.get("name")
                ctype = c.get("uidt") or c.get("type") or "?"
                print(f"   - {ctitle} ({ctype})")
        else:
            try:
                sample = await client.fetch_table(t)
                if sample:
                    row = normalize_row(sample[0])
                    print(f"   columns: {', '.join(row.keys())}")
                    print(f"   rows: {len(sample)}+ (sample loaded)")
                else:
                    print("   (empty table)")
            except Exception as e:
                print(f"   (could not load sample: {e})")
        print()
