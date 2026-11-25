"""Schakelaar: zonnestroom terugleveren als de accu vol is."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity

PARALLEL_UPDATES = 0

# gridReverse: 1 = terugleveren toegestaan, 2 = verboden
ALLOWED = 1
FORBIDDEN = 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.data.has("gridReverse"):
        async_add_entities([PvExportSwitch(coordinator)])


class PvExportSwitch(ZendureEntity, SwitchEntity):
    """Aan = overschot van de zonnepanelen op de batterij mag het net op."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:solar-power-variant"

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "pv_export")

    @property
    def is_on(self) -> bool | None:
        value = int(self.coordinator.data.get("gridReverse"))
        if value == ALLOWED:
            return True
        if value == FORBIDDEN:
            return False
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write_setting({"gridReverse": ALLOWED})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write_setting({"gridReverse": FORBIDDEN})
