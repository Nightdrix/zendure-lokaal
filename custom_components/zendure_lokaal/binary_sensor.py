"""Aan/uit-sensoren: HEMS, accuverwarming en storing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity
from .models import ZendureData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ZendureBinaryDescription(BinarySensorEntityDescription):
    prop: str
    is_on_fn: Callable[[ZendureData, str], bool] = lambda d, p: int(d.get(p)) == 1


BINARY_SENSORS: tuple[ZendureBinaryDescription, ...] = (
    ZendureBinaryDescription(
        key="hems_state",
        translation_key="hems_state",
        prop="hemsState",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureBinaryDescription(
        key="heat_state",
        translation_key="heat_state",
        prop="heatState",
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    ZendureBinaryDescription(
        key="error",
        translation_key="error",
        prop="is_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda d, p: int(d.get(p)) != 0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ZendureBinarySensor(coordinator, d) for d in BINARY_SENSORS if coordinator.data.has(d.prop))


class ZendureBinarySensor(ZendureEntity, BinarySensorEntity):
    entity_description: ZendureBinaryDescription

    def __init__(self, coordinator: ZendureCoordinator, description: ZendureBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        d = self.entity_description
        return d.is_on_fn(self.coordinator.data, d.prop)
