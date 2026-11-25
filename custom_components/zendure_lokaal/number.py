"""Schuifjes: laad-/ontlaadvermogen, min/max laadniveau en handmatig vermogen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity
from .models import ZendureData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ZendureNumberDescription(NumberEntityDescription):
    value_fn: Callable[[ZendureData], float]
    write_fn: Callable[[float], dict[str, Any]]
    max_fn: Callable[[ZendureData], float] | None = None


def _input_limit(value: float) -> dict[str, Any]:
    if value > 0:
        return {"smartMode": 1, "acMode": 1, "inputLimit": int(value)}
    return {"inputLimit": 0}


def _output_limit(value: float) -> dict[str, Any]:
    if value > 0:
        return {"smartMode": 1, "acMode": 2, "outputLimit": int(value)}
    return {"outputLimit": 0}


NUMBERS: tuple[ZendureNumberDescription, ...] = (
    ZendureNumberDescription(
        key="input_limit",
        translation_key="input_limit",
        icon="mdi:battery-arrow-up",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda d: d.input_limit,
        write_fn=_input_limit,
        max_fn=lambda d: d.max_charge_limit,
    ),
    ZendureNumberDescription(
        key="output_limit",
        translation_key="output_limit",
        icon="mdi:battery-arrow-down",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda d: d.output_limit,
        write_fn=_output_limit,
        max_fn=lambda d: d.max_discharge_limit,
    ),
    ZendureNumberDescription(
        key="soc_set",
        translation_key="soc_set",
        icon="mdi:battery-high",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda d: d.soc_max,
        write_fn=lambda v: {"socSet": int(round(v * 10))},
    ),
    ZendureNumberDescription(
        key="min_soc",
        translation_key="min_soc",
        icon="mdi:battery-low",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda d: d.soc_min,
        write_fn=lambda v: {"minSoc": int(round(v * 10))},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [ZendureNumber(coordinator, d) for d in NUMBERS]
    entities.append(ManualPowerNumber(coordinator))
    async_add_entities(entities)


class ZendureNumber(ZendureEntity, NumberEntity):
    """Instelling die rechtstreeks op de batterij staat."""

    entity_description: ZendureNumberDescription

    def __init__(self, coordinator: ZendureCoordinator, description: ZendureNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_max_value(self) -> float:
        if self.entity_description.max_fn is not None:
            return self.entity_description.max_fn(self.coordinator.data)
        return super().native_max_value

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_setting(self.entity_description.write_fn(value))


class ManualPowerNumber(ZendureEntity, RestoreNumber):
    """Vast vermogen voor de modus 'Handmatig'. + = ontladen, - = laden."""

    _attr_icon = "mdi:knob"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_step = 10
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "manual_power")
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
            self.coordinator.manual_power = last.native_value

    @property
    def native_min_value(self) -> float:
        return -self.coordinator.data.max_charge_limit

    @property
    def native_max_value(self) -> float:
        return self.coordinator.data.max_discharge_limit

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        await self.coordinator.async_set_manual_power(value)
        self.async_write_ha_state()
