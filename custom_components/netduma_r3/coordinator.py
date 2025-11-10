from __future__ import annotations

import time
from collections import defaultdict
from typing import Any
import logging
from datetime import timedelta
from homeassistant.helpers.event import async_track_time_interval


from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from datetime import timedelta
from homeassistant.helpers.event import async_track_time_interval
from .client import DumaOSClient
from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_TREE_INTERVAL, DEFAULT_SYS_INTERVAL

class NetdumaDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.session = async_get_clientsession(hass)
        self.client = DumaOSClient(
            entry.data["host"],
            self.session,
            verify_ssl=entry.data.get("verify_ssl", False),
            username=entry.data.get("username"),
            password=entry.data.get("password"),
        )
        super().__init__(
            hass,
            logger=hass.logger,
            name="netduma_r3",
            update_interval=None,  # manual scheduling per‑task
        )
        # internal state
        self._last_bytes: dict[str, dict[str, int]] = defaultdict(lambda: {"rx": 0, "tx": 0})
        self._last_ts = 0.0

    async def async_config_entry_first_refresh(self) -> None:
        await self._refresh_full()
        # schedule periodic tasks
        self.async_set_update_error(None)
        self._schedule_tasks()

    def _schedule_tasks(self) -> None:
        async_track_time_interval(self.hass, self._refresh_presence, timedelta(seconds=DEFAULT_SCAN_INTERVAL))
        async_track_time_interval(self.hass, self._refresh_trees, timedelta(seconds=DEFAULT_TREE_INTERVAL))
        async_track_time_interval(self.hass, self._refresh_system, timedelta(seconds=DEFAULT_SYS_INTERVAL))


    async def _refresh_full(self, *_):
        devices = await self.client.get_all_devices()
        online = await self.client.get_valid_online_interfaces()
        up = await self.client.get_upload_tree()
        down = await self.client.get_download_tree()
        sys = await self.client.get_system_info()
        self._merge_state(devices, online, up, down, sys)
        self.async_set_updated_data(self.data)

    async def _refresh_presence(self, *_):
        try:
            online = await self.client.get_valid_online_interfaces()
            self._merge_presence(online)
            self.async_set_updated_data(self.data)
        except Exception as err:  # keep running
            self.async_set_update_error(err)

    async def _refresh_trees(self, *_):
        try:
            up = await self.client.get_upload_tree()
            down = await self.client.get_download_tree()
            self._merge_traffic(up, down)
            self.async_set_updated_data(self.data)
        except Exception as err:
            self.async_set_update_error(err)

    async def _refresh_system(self, *_):
        try:
            sys = await self.client.get_system_info()
            self.data.setdefault("system", {}).update(sys or {})
            self.async_set_updated_data(self.data)
        except Exception as err:
            self.async_set_update_error(err)

    def _merge_state(self, devices, online, up, down, sys):
        self.data = {
            "devices": self._index_devices(devices or []),
            "presence": self._presence_map(online or []),
            "traffic": self._traffic_from_trees(up or {}, down or {}),
            "system": sys or {},
        }
        self._last_ts = time.time()
        # seed last bytes for delta
        for devid, t in self.data["traffic"].items():
            self._last_bytes[devid] = {"rx": t.get("rx_bytes", 0), "tx": t.get("tx_bytes", 0)}

    def _merge_presence(self, online):
        self.data.setdefault("presence", {}).update(self._presence_map(online or []))

    def _merge_traffic(self, up, down):
        now = time.time()
        dt = max(1.0, now - (self._last_ts or now))
        self._last_ts = now

        merged = self._traffic_from_trees(up or {}, down or {})
        for devid, t in merged.items():
            last = self._last_bytes[devid]
            rx, tx = t.get("rx_bytes", 0), t.get("tx_bytes", 0)
            t["rx_rate_bps"] = (rx - last.get("rx", 0)) / dt
            t["tx_rate_bps"] = (tx - last.get("tx", 0)) / dt
            self._last_bytes[devid] = {"rx": rx, "tx": tx}
        self.data.setdefault("traffic", {}).update(merged)

    def _index_devices(self, devices):
        out = {}
        for d in devices:
            devid = str(d.get("devid"))
            name = d.get("uhost") or d.get("hostname") or f"device_{devid}"
            # interfaces is a list of dicts with mac
            macs = [i.get("mac") for i in d.get("interfaces", []) if i.get("mac")]
            out[devid] = {"name": name, "macs": macs}
        return out

    def _presence_map(self, online):
        mac_online = {i.get("mac"): True for i in online if i.get("mac")}
        present = {}
        for devid, meta in self.data.get("devices", {}).items():
            present[devid] = any(mac_online.get(m) for m in meta.get("macs", []))
        return present

    def _traffic_from_trees(self, up_tree, down_tree):
        # Each tree has AutoAlloc.bandwidth_allocations with bytes and match.devid
        acc: dict[str, dict[str, int]] = {}
        for tree, key in [(down_tree, "rx_bytes"), (up_tree, "tx_bytes")]:
            try:
                ba = (
                    tree.get("AutoAlloc", {}).get("bandwidth_allocations")
                    or tree.get("AutoAlloc", {}).get("BandwidthAllocations")
                    or []
                )
                for item in ba:
                    devid = str(item.get("match", {}).get("devid"))
                    bytes_val = int(item.get("bytes", 0))
                    acc.setdefault(devid, {"rx_bytes": 0, "tx_bytes": 0})
                    acc[devid][key] += bytes_val
            except Exception:
                continue
        return acc
