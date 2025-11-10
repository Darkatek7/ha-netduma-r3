# imports unchanged
import aiohttp
import json
import logging
from typing import Any

log = logging.getLogger(__name__)
JSON = dict[str, Any]

class DumaOSClient:
    def __init__(self, host: str, session: aiohttp.ClientSession, *,
                 verify_ssl: bool=False, username: str|None=None, password: str|None=None) -> None:
        self._host = host
        self._session = session
        self._verify_ssl = verify_ssl
        self._username = username
        self._password = password
        self._id = 0
        self._base = None  # will be "http://..." or "https://..."
        self._headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _schemes(self) -> list[str]:
        # prefer https, then http
        return ["https", "http"]

    async def _ensure_base(self) -> None:
        if self._base:
            return
        probe = {"jsonrpc":"2.0","id":0,"clienttype":"web","method":"get_system_info","params":[]}
        auth = aiohttp.BasicAuth(self._username, self._password) if (self._username and self._password) else None
        last_err = None
        for scheme in self._schemes():
            base = f"{scheme}://{self._host}"
            url = f"{base}/apps/com.netdumasoftware.systeminfo/rpc/"
            try:
                async with self._session.post(
                    url, data=json.dumps(probe), headers=self._headers,
                    ssl=(self._verify_ssl if scheme == "https" else None),
                    auth=auth, allow_redirects=True
                ) as r:
                    log.debug("Probe %s -> %s", url, r.status)
                    if r.status == 401 and not auth:
                        raise RuntimeError("Router requires credentials. Set username and password in options.")
                    if 200 <= r.status < 300:
                        self._base = base
                        return
                    last_err = f"{url} -> {r.status}"
            except aiohttp.ClientError as e:
                last_err = f"{url} -> {e}"
                continue
        raise RuntimeError(f"Unable to reach Netduma RPC. Last error: {last_err}")

    async def _rpc(self, app: str, method: str, params: list[Any] | None=None) -> Any:
        await self._ensure_base()
        self._id += 1
        url = f"{self._base}/apps/{app}/rpc/"
        payload = {"jsonrpc":"2.0","id":self._id,"clienttype":"web","method":method,"params":params or []}
        auth = aiohttp.BasicAuth(self._username, self._password) if (self._username and self._password) else None

        for attempt in (0, 1):
            async with self._session.post(
                url, data=json.dumps(payload), headers=self._headers,
                ssl=(self._base.startswith("https") and self._verify_ssl) or None,
                auth=auth, allow_redirects=True
            ) as r:
                if r.status == 401 and auth is None and attempt == 0:
                    raise RuntimeError("Router requires credentials. Set username and password in options.")
                r.raise_for_status()
                data = await r.json(content_type=None)
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
        if isinstance(res, list) and res:
            return res[0]
        return res or {}

def _parse_tree(result_any: Any) -> dict:
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
