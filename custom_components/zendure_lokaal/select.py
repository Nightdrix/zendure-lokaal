"""Keuzemenu's: Bedrijfsmodus en AC-modus."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import AC_MODE_VALUES, AC_MODES, OPERATION_MODES
from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([OperationSelect(coordinator), AcModeSelect(coordinator)])


class OperationSelect(ZendureEntity, SelectEntity, RestoreEntity):
    """Bedrijfsmodus: wat moet de batterij automatisch doen?

    De waarden (off/manual/smart/...) zijn gelijk aan de officiële Zendure-integratie,
    zodat de Energienerds-planner deze keuzelijst direct kan aansturen.
    """

    _attr_options = OPERATION_MODES
    _attr_icon = "mdi:home-battery"

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "operation")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        mode = self.coordinator.start_mode
        if (last := await self.async_get_last_state()) is not None and last.state in OPERATION_MODES:
            mode = last.state
        await self.coordinator.async_set_operation(mode, restored=True)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.operation

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_operation(option)
        self.async_write_ha_state()


class AcModeSelect(ZendureEntity, SelectEntity):
    """AC-modus: laden (invoer) of ontladen (uitvoer). Vooral voor de planner."""

    _attr_options = list(AC_MODES.values())
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:swap-vertical"

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "ac_mode")

    @property
    def current_option(self) -> str | None:
        return AC_MODES.get(self.coordinator.data.ac_mode)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_write_setting({"acMode": AC_MODE_VALUES[option]})
