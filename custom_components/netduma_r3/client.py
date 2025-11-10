from __future__ import annotations
import json
from typing import Any
import aiohttp
import logging

log = logging.getLogger(__name__)
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
        self._headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _schemes(self) -> list[str]:
        return ["https", "http"]

    async def _seed_and_csrf(self, base: str) -> dict[str, str]:
        try:
            async with self._session.get(
                f"{base}/",
                ssl=(self._verify_ssl if base.startswith("https") else None),
                allow_redirects=True,
            ):
                pass
        except aiohttp.ClientError as e:
            log.debug("Seed GET failed on %s: %s", base, e)
            return {}
        xsrf = None
        for c in self._session.cookie_jar:
            if c.key.lower() in ("xsrf-token", "csrftoken", "csrf_token"):
                xsrf = c.value
                break
        return {"X-XSRF-TOKEN": xsrf} if xsrf else {}

    async def _ensure_session(self) -> None:
        if not (self._username and self._password):
            return

        last_url = None
        last_status = None

        # Probe RPC with Basic on both schemes
        probe_payload = {"jsonrpc": "2.0", "id": 0, "clienttype": "web", "method": "get_system_info", "params": []}
        for scheme in self._schemes():
            base = f"{scheme}://{self._host}"
            url = f"{base}/apps/com.netdumasoftware.systeminfo/rpc/"
            try:
                async with self._session.post(
                    url,
                    data=json.dumps(probe_payload),
                    headers=self._headers,
                    ssl=(self._verify_ssl if scheme == "https" else None),
                    auth=aiohttp.BasicAuth(self._username, self._password),
                    allow_redirects=True,
                ) as resp:
                    last_url, last_status = url, resp.status
                    log.debug("Probe %s -> %s", url, resp.status)
                    if resp.status != 401:
                        self._base = base
                        return
            except aiohttp.ClientError as e:
                log.debug("Probe error on %s: %s", url, e)

        # Cookie session on both schemes
        for scheme in self._schemes():
            base = f"{scheme}://{self._host}"
            csrf_headers = await self._seed_and_csrf(base)
            common_headers = {"Origin": base, "Referer": f"{base}/"}

            # Form endpoints
            form = aiohttp.FormData()
            form.add_field("username", self._username)
            form.add_field("password", self._password)
            for ep in ("/login", "/duma/login"):
                url = f"{base}{ep}"
                try:
                    async with self._session.post(
                        url,
                        data=form,
                        headers={**csrf_headers, **common_headers},
                        ssl=(self._verify_ssl if scheme == "https" else None),
                        allow_redirects=True,
                    ) as lr:
                        last_url, last_status = url, lr.status
                        log.debug("Form login %s -> %s", url, lr.status)
                        if lr.status in (200, 204):
                            self._base = base
                            return
                except aiohttp.ClientError as e:
                    log.debug("Form login error on %s: %s", url, e)

            # JSON endpoints
            js = {"username": self._username, "password": self._password, "remember": True}
            for ep in ("/dumaos/api/login", "/api/login"):
                url = f"{base}{ep}"
                try:
                    async with self._session.post(
                        url,
                        json=js,
                        headers={**csrf_headers, **common_headers},
                        ssl=(self._verify_ssl if scheme == "https" else None),
                        allow_redirects=True,
                    ) as lr:
                        last_url, last_status = url, lr.status
                        log.debug("JSON login %s -> %s", url, lr.status)
                        if lr.status in (200, 204):
                            self._base = base
                            return
                except aiohttp.ClientError as e:
                    log.debug("JSON login error on %s: %s", url, e)

        # Make the failure readable in HA logs
        raise RuntimeError(f"Netduma auth failed. Last endpoint {last_url} returned {last_status}")

    async def _rpc(self, app: str, method: str, params: list[Any] | None = None) -> Any:
        self._id += 1
        await self._ensure_session()
        url = f"{self._base}/apps/{app}/rpc/"
        payload = {"jsonrpc": "2.0", "id": self._id, "clienttype": "web", "method": method, "params": params or []}
        auth = aiohttp.BasicAuth(self._username, self._password) if (self._username and self._password) else None

        for attempt in (0, 1):
            async with self._session.post(
                url,
                data=json.dumps(payload),
                headers=self._headers,
                ssl=(self._verify_ssl if self._base.startswith("https") else None),
                auth=(auth if attempt == 0 else None),
                allow_redirects=True,
            ) as resp:
                if resp.status == 401 and attempt == 0:
                    log.debug("RPC 401 on %s with Basic. Retrying with cookies only.", url)
                    continue
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
