"""Zendure Lokaal: Zendure-batterij 100% lokaal in Home Assistant (zenSDK)."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event

from .api import ZendureClient
from .const import CONF_HOST, DOMAIN
from .coordinator import ZendureConfigEntry, ZendureCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ZendureConfigEntry) -> bool:
    """Batterij koppelen."""
    client = ZendureClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    coordinator = ZendureCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    if not coordinator.data:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": client.host},
        )

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_change))
    # Elke nieuwe meterstand van de P1-meter: direct bijsturen.
    entry.async_on_unload(async_track_state_change_event(hass, coordinator.p1_entities(), coordinator.async_p1_changed))
    return True


async def _async_reload_on_change(hass: HomeAssistant, entry: ZendureConfigEntry) -> None:
    """Instellingen gewijzigd: opnieuw laden met de nieuwe waarden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZendureConfigEntry) -> bool:
    """Batterij ontkoppelen (bij herstart, wijziging of verwijderen)."""
    coordinator = entry.runtime_data
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # Niemand regelt nu meer bij: batterij stilzetten zodat hij niet blijft
        # (ont)laden met een oud vermogen.
        await coordinator.async_stop()
    return unloaded
