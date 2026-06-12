#!/usr/bin/env python3
"""Проверка подключения к 3X-UI с VPS: python3 scripts/test_xui.py"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from bot.config import Config
from bot.services.xui_client import XUIClient


async def main() -> int:
    cfg = Config()
    xui = XUIClient(
        host=cfg.XUI_HOST,
        url_prefix=cfg.XUI_URL_PREFIX,
        username=cfg.XUI_USERNAME,
        password=cfg.XUI_PASSWORD,
        api_token=cfg.XUI_API_TOKEN,
        sub_path=cfg.XUI_SUB_PATH,
    )

    print("Panel:", f"{cfg.XUI_HOST}{cfg.XUI_URL_PREFIX}")
    print("API token:", "yes" if cfg.XUI_API_TOKEN else "no (login/password)")
    print("Inbounds config:", cfg.XUI_INBOUND_IDS)

    try:
        status = await xui.get_server_status()
        xray = status.get("xray", status) if isinstance(status, dict) else status
        print("OK server/status:", xray if isinstance(xray, str) else "connected")
    except Exception as e:
        print("FAIL server/status:", e)
        return 1

    try:
        inbounds = await xui.list_inbounds()
        print(f"OK inbounds/list: {len(inbounds)} inbound(s)")
        for ib in inbounds[:10]:
            print(f"  - id={ib.get('id')} remark={ib.get('remark')} protocol={ib.get('protocol')} enable={ib.get('enable')}")
    except Exception as e:
        print("FAIL inbounds/list:", e)
        return 1

    inbound_id = list(cfg.XUI_INBOUND_IDS.values())[0]
    if not any(int(ib.get("id", -1)) == inbound_id for ib in inbounds):
        print(f"WARN: INBOUND_RU={inbound_id} not found in panel — fix INBOUND_* in .env")
        return 1

    try:
        result = await xui.add_client(
            inbound_id=inbound_id,
            first_name="test",
            last_name="bot",
            telegram_id=0,
            months=1,
            limit_ip=1,
            traffic_gb=1,
        )
        print("OK add_client:", result["email"])
        await xui.delete_client(inbound_id, result["uuid"], result["email"])
        print("OK delete test client")
    except Exception as e:
        print("FAIL add_client:", e)
        return 1

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
