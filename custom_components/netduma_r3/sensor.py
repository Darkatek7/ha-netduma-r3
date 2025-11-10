from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import NetdumaDataCoordinator
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]  # ← reuse
    entities = []
    entities.append(RouterUptimeSensor(coordinator))
    entities.append(RouterFirmwareSensor(coordinator))
    for devid, meta in coordinator.data.get("devices", {}).items():
        name = meta.get("name", devid)
        entities += [
            DeviceBytesSensor(coordinator, devid, name, "rx"),
            DeviceBytesSensor(coordinator, devid, name, "tx"),
            DeviceRateSensor(coordinator, devid, name, "rx"),
            DeviceRateSensor(coordinator, devid, name, "tx"),
        ]
    async_add_entities(entities)

class BaseNetdumaSensor(CoordinatorEntity[NetdumaDataCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator: NetdumaDataCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self):
        host = self.coordinator.entry.data["host"]
        sys = self.coordinator.data.get("system", {}) or {}
        return {
            "identifiers": {("netduma_r3", host)},
            "manufacturer": "Netduma",
            "model": sys.get("board", "R3"),
            "name": f"Netduma R3 ({host})",
            "sw_version": sys.get("version"),
        }

class RouterUptimeSensor(BaseNetdumaSensor):
    def __init__(self, coordinator: NetdumaDataCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Router uptime"
        self._attr_unique_id = f"{coordinator.entry.data['host']}_uptime"
        self._attr_icon = "mdi:timer-outline"
        self._attr_native_unit_of_measurement = "s"

    @property
    def native_value(self) -> Any:
        return (self.coordinator.data.get("system", {}) or {}).get("uptime")

class RouterFirmwareSensor(BaseNetdumaSensor):
    def __init__(self, coordinator: NetdumaDataCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "Router firmware"
        self._attr_unique_id = f"{coordinator.entry.data['host']}_fw"
        self._attr_icon = "mdi:update"

    @property
    def native_value(self) -> Any:
        return (self.coordinator.data.get("system", {}) or {}).get("version")

class DeviceBytesSensor(BaseNetdumaSensor):
    def __init__(self, coordinator: NetdumaDataCoordinator, devid: str, name: str, dir_key: str) -> None:
        super().__init__(coordinator)
        self.devid = devid
        self.dir_key = dir_key  # "rx" or "tx"
        self._attr_name = f"{name} {dir_key.upper()} bytes"
        self._attr_unique_id = f"{coordinator.entry.data['host']}_{devid}_{dir_key}_bytes"
        self._attr_native_unit_of_measurement = "byte"
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> Any:
        t = self.coordinator.data.get("traffic", {}).get(self.devid, {})
        return t.get(f"{self.dir_key}_bytes")

class DeviceRateSensor(BaseNetdumaSensor):
    def __init__(self, coordinator: NetdumaDataCoordinator, devid: str, name: str, dir_key: str) -> None:
        super().__init__(coordinator)
        self.devid = devid
        self.dir_key = dir_key
        self._attr_name = f"{name} {dir_key.upper()} rate"
        self._attr_unique_id = f"{coordinator.entry.data['host']}_{devid}_{dir_key}_rate"
        self._attr_native_unit_of_measurement = "B/s"
        self._attr_icon = "mdi:swap-vertical"

    @property
    def native_value(self) -> Any:
        t = self.coordinator.data.get("traffic", {}).get(self.devid, {})
        return t.get(f"{self.dir_key}_rate_bps")
