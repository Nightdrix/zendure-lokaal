"""Diagnose-download (handig bij hulpvragen)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import ZendureConfigEntry

TO_REDACT = {"sn", "serial", "host", "ip", "wifiName", "ssid", "mac"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ZendureConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "settings": async_redact_data(coordinator.settings, TO_REDACT),
        "operation": coordinator.operation,
        "status": coordinator.status,
        "target": coordinator.target,
        "p1": coordinator.p1_value,
        "report": async_redact_data(coordinator.data.raw if coordinator.data else {}, TO_REDACT),
    }
