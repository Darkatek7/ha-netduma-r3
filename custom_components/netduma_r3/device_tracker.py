from __future__ import annotations

from homeassistant.components.device_tracker import TrackerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import NetdumaDataCoordinator

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = NetdumaDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entities: list[TrackerEntity] = []
    for devid, meta in coordinator.data.get("devices", {}).items():
        name = meta.get("name", devid)
        entities.append(NetdumaTracker(coordinator, devid, name))
    async_add_entities(entities)

class NetdumaTracker(CoordinatorEntity[NetdumaDataCoordinator], TrackerEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: NetdumaDataCoordinator, devid: str, name: str) -> None:
        super().__init__(coordinator)
        self.devid = devid
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.entry.data['host']}_{devid}_presence"

    @property
    def is_connected(self) -> bool:
        return bool(self.coordinator.data.get("presence", {}).get(self.devid))

    @property
    def source_type(self) -> SourceType:
        return SourceType.ROUTER
