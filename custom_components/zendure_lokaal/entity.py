"""Basis voor alle Zendure Lokaal-entiteiten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ZendureCoordinator


def device_info(coordinator: ZendureCoordinator) -> DeviceInfo:
    data = coordinator.data
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.serial)},
        name=data.name if data else coordinator.config_entry.title,
        manufacturer=MANUFACTURER,
        model=data.name if data else None,
        model_id=data.product if data else None,
        serial_number=coordinator.serial,
        configuration_url=f"http://{coordinator.client.host}/{'properties/report'}",
    )


class ZendureEntity(CoordinatorEntity[ZendureCoordinator]):
    """Gemeenschappelijke basis: naam via vertaling, gekoppeld aan het apparaat."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZendureCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.serial}_{key}"
        self._attr_device_info = device_info(coordinator)
