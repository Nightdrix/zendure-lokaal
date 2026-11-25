"""Knop: in één keer koppelen aan de Energienerds-planner."""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .const import DOMAIN, PLANNER_DOMAIN
from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Welke van onze entiteiten bij welk veld van de planner hoort.
PLANNER_FIELDS: dict[str, tuple[str, str]] = {
    "operation_entity": ("select", "operation"),
    "direction_entity": ("select", "ac_mode"),
    "charge_power_entity": ("number", "input_limit"),
    "discharge_power_entity": ("number", "output_limit"),
    "charge_soc_entity": ("number", "soc_set"),
    "discharge_soc_entity": ("number", "min_soc"),
}

MESSAGES = {
    "nl": (
        "Energienerds-planner gekoppeld",
        "De planner is gekoppeld aan je {name}.\n\n"
        "Laatste stap: open je dashboard, klik op het potloodje (bewerken), "
        "kies **Kaart toevoegen** en zoek op **schedule**. "
        "Ververs de pagina (Ctrl+F5) als de kaart niet in de lijst staat.",
    ),
    "en": (
        "Energienerds planner linked",
        "The planner is now linked to your {name}.\n\n"
        "Last step: open your dashboard, click the pencil (edit), choose "
        "**Add card** and search for **schedule**. Refresh the page (Ctrl+F5) "
        "if the card is not listed.",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LinkPlannerButton(entry.runtime_data)])


class LinkPlannerButton(ZendureEntity, ButtonEntity):
    """Maakt automatisch de Energienerds-planner aan met de juiste entiteiten."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "link_planner")

    async def async_press(self) -> None:
        hass = self.hass
        try:
            await async_get_integration(hass, PLANNER_DOMAIN)
        except IntegrationNotFound as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="planner_not_installed") from err

        registry = er.async_get(hass)
        serial = self.coordinator.serial
        data: dict[str, object] = {"name": f"Zendure planner {self.coordinator.data.name}"}
        for field, (platform, key) in PLANNER_FIELDS.items():
            entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{serial}_{key}")
            if entity_id is None:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="planner_link_failed")
            data[field] = entity_id
        data["max_power"] = max(self.coordinator.data.max_charge_limit, self.coordinator.data.max_discharge_limit)

        for planner in hass.config_entries.async_entries(PLANNER_DOMAIN):
            if planner.data.get("operation_entity") == data["operation_entity"]:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="planner_already_linked")

        result = await hass.config_entries.flow.async_init(PLANNER_DOMAIN, context={"source": SOURCE_USER}, data=data)
        if result.get("type") != FlowResultType.CREATE_ENTRY:
            _LOGGER.warning("Planner koppelen gaf: %s", result)
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="planner_link_failed")

        lang = "nl" if str(hass.config.language).startswith("nl") else "en"
        title, message = MESSAGES[lang]
        persistent_notification.async_create(
            hass,
            message.format(name=self.coordinator.data.name),
            title=title,
            notification_id=f"{DOMAIN}_planner_{serial}",
        )
