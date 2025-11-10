from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

JSON = dict[str, Any]

class DumaOSClient:
    """Minimal JSON‑RPC client for DumaOS apps on the R3.

    Expected endpoints:
      https://<host>/apps/<app-id>/rpc/
    """

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        verify_ssl: bool = False,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        # Many R3 firmwares use a self‑signed cert on HTTPS
        self._base = f"https://{host}"
        self._session = session
        self._verify_ssl = verify_ssl
        self._username = username
        self._password = password
        self._id = 0
        self._headers = {"Content-Type": "application/json"}

    async def _rpc(self, app: str, method: str, params: list[Any] | None = None) -> Any:
        self._id += 1
        url = f"{self._base}/apps/{app}/rpc/"
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "clienttype": "web",
            "method": method,
            "params": params or [],
        }
        auth = None
        if self._username and self._password:
            auth = aiohttp.BasicAuth(self._username, self._password)
        async with self._session.post(
            url,
            data=json.dumps(payload),
            headers=self._headers,
            ssl=self._verify_ssl,
            auth=auth,
        ) as resp:
            if resp.status == 401:
                # If the router uses cookie login, add it later here
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=401)
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        if "error" in data:
            raise RuntimeError(f"RPC error {data['error']}")
        return data.get("result")

    # Devices
    async def get_all_devices(self) -> list[JSON]:
        return await self._rpc("com.netdumasoftware.devicemanager", "get_all_devices")

    async def get_valid_online_interfaces(self) -> list[JSON]:
        return await self._rpc("com.netdumasoftware.devicemanager", "get_valid_online_interfaces")

    async def get_dhcp_leases(self) -> list[JSON]:
        return await self._rpc("com.netdumasoftware.devicemanager", "get_dhcp_leases")

    # QoS trees
    async def get_upload_tree(self) -> dict:
        res = await self._rpc("com.netdumasoftware.smartqos", "get_upload_tree")
        return _parse_tree(res)

    async def get_download_tree(self) -> dict:
        res = await self._rpc("com.netdumasoftware.smartqos", "get_download_tree")
        return _parse_tree(res)

    async def get_throt_percentage(self) -> list[int]:
        return await self._rpc("com.netdumasoftware.smartqos", "get_throt_percentage")

    # System
    async def get_system_info(self) -> dict:
        res = await self._rpc("com.netdumasoftware.systeminfo", "get_system_info")
        # Some firmwares wrap single dict inside a list
        if isinstance(res, list) and res:
            return res[0]
        return res or {}


def _parse_tree(result_any: Any) -> dict:
    """smartqos returns a JSON string inside result; unwrap it."""
    # Expected shapes seen in HAR: ["{...json...}"] or "{...json...}"
    if isinstance(result_any, list) and result_any:
        inner = result_any[0]
    else:
        inner = result_any
    if isinstance(inner, str):
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            return {}
    if isinstance(inner, dict):
        return inner
    return {}
