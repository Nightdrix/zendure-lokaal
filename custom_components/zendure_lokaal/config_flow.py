"""Instelscherm voor Zendure Lokaal."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import network
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import async_probe, async_scan, hosts_in_networks
from .const import (
    CONF_CAPACITY,
    CONF_CHARGE_MARGIN,
    CONF_CHARGE_START,
    CONF_DISCHARGE_MARGIN,
    CONF_DISCHARGE_START,
    CONF_HOST,
    CONF_INTERVAL,
    CONF_MAX_CHARGE,
    CONF_MAX_DISCHARGE,
    CONF_P1_EXPORT_SENSOR,
    CONF_P1_INVERT,
    CONF_P1_SENSOR,
    CONF_STANDBY_MINUTES,
    CONF_START_MODE,
    DEFAULT_CAPACITY,
    DEFAULT_CHARGE_MARGIN,
    DEFAULT_CHARGE_START,
    DEFAULT_DISCHARGE_MARGIN,
    DEFAULT_DISCHARGE_START,
    DEFAULT_INTERVAL,
    DEFAULT_MAX_POWER,
    DEFAULT_STANDBY_MINUTES,
    DOMAIN,
    MODE_SMART,
    SECTION_ADVANCED,
    START_MODES,
)
from .coordinator import entry_settings
from .models import ZendureData

_LOGGER = logging.getLogger(__name__)


# ------------------------------------------------------------------ selectors
def _watt(minimum: int, maximum: int, step: int = 10) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement="W",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _number(minimum: float, maximum: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


P1_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.POWER)
)


def _p1_schema() -> dict[Any, Any]:
    return {
        vol.Required(CONF_P1_SENSOR): P1_SELECTOR,
        vol.Optional(CONF_P1_EXPORT_SENSOR): P1_SELECTOR,
        vol.Optional(CONF_P1_INVERT, default=False): selector.BooleanSelector(),
    }


def _power_schema(device_charge: int, device_discharge: int) -> dict[Any, Any]:
    """Maximaal laad-/ontlaadvermogen; nooit meer dan het apparaat zelf kan."""
    return {
        vol.Required(CONF_MAX_CHARGE, default=device_charge): _watt(100, max(device_charge, 100)),
        vol.Required(CONF_MAX_DISCHARGE, default=device_discharge): _watt(100, max(device_discharge, 100)),
    }


def _advanced_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_DISCHARGE_START, default=DEFAULT_DISCHARGE_START): _watt(20, 1000),
            vol.Required(CONF_CHARGE_START, default=DEFAULT_CHARGE_START): _watt(20, 1500),
            vol.Required(CONF_DISCHARGE_MARGIN, default=DEFAULT_DISCHARGE_MARGIN): _watt(0, 250, 1),
            vol.Required(CONF_CHARGE_MARGIN, default=DEFAULT_CHARGE_MARGIN): _watt(0, 250, 1),
            vol.Required(CONF_STANDBY_MINUTES, default=DEFAULT_STANDBY_MINUTES): _number(0, 120, 1, "min"),
            vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): _number(2, 30, 1, "s"),
            vol.Required(CONF_CAPACITY, default=DEFAULT_CAPACITY): _number(0, 100, 0.01, "kWh"),
        }
    )


def _p1_error(hass: HomeAssistant, user_input: dict[str, Any]) -> str | None:
    """Controleer of de gekozen P1-sensor(en) een getal geven."""
    for key in (CONF_P1_SENSOR, CONF_P1_EXPORT_SENSOR):
        entity_id = user_input.get(key)
        if not entity_id:
            continue
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return "p1_no_value"
        try:
            float(state.state)
        except ValueError:
            return "p1_no_value"
    if user_input.get(CONF_P1_EXPORT_SENSOR) == user_input.get(CONF_P1_SENSOR):
        return "p1_same_sensor"
    return None


async def _local_networks(hass: HomeAssistant) -> list[str]:
    networks: list[str] = []
    for adapter in await network.async_get_adapters(hass):
        if not adapter.get("enabled"):
            continue
        for ip in adapter.get("ipv4", []):
            networks.append(f"{ip['address']}/{ip['network_prefix']}")
    return networks


class ZendureLokaalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Stap voor stap een batterij koppelen."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str = ""
        self._report: dict[str, Any] = {}
        self._found: dict[str, dict[str, Any]] = {}
        self._p1: dict[str, Any] = {}

    @property
    def _data(self) -> ZendureData:
        return ZendureData.from_report(self._report)

    # Stap 1: waar staat de batterij?
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input.get(CONF_HOST) or "").strip()
            session = async_get_clientsession(self.hass)
            if not host:
                hosts = hosts_in_networks(await _local_networks(self.hass))
                self._found = await async_scan(session, hosts) if hosts else {}
                if len(self._found) == 1:
                    host, report = next(iter(self._found.items()))
                    return await self._async_use_device(host, report)
                if len(self._found) > 1:
                    return await self.async_step_pick()
                errors["base"] = "not_found"
            else:
                report = await async_probe(session, host, timeout=5)
                if report is None:
                    errors["base"] = "cannot_connect"
                else:
                    return await self._async_use_device(host, report)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_HOST, default=""): str}),
            errors=errors,
        )

    # Stap 1b: meerdere batterijen gevonden -> kiezen
    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            host = user_input[CONF_HOST]
            return await self._async_use_device(host, self._found[host])
        options = [
            selector.SelectOptionDict(
                value=host,
                label=f"{ZendureData.from_report(report).name} – {host}",
            )
            for host, report in sorted(self._found.items())
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST): selector.SelectSelector(selector.SelectSelectorConfig(options=options))}
            ),
        )

    async def _async_use_device(self, host: str, report: dict[str, Any]) -> ConfigFlowResult:
        self._host = host
        self._report = report
        serial = self._data.serial or host
        # raise_on_progress=False: een half afgemaakte eerdere poging blokkeert niet.
        await self.async_set_unique_id(serial, raise_on_progress=False)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        return await self.async_step_p1()

    # Stap 2: welke slimme meter?
    async def async_step_p1(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := _p1_error(self.hass, user_input)) is None:
                self._p1 = user_input
                return await self.async_step_settings()
            errors["base"] = error
        data = self._data
        return self.async_show_form(
            step_id="p1",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(_p1_schema()), user_input or {}),
            errors=errors,
            description_placeholders={"name": data.name, "serial": data.serial, "host": self._host},
        )

    # Stap 3: basisinstellingen
    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        data = self._data
        if user_input is not None:
            options = {
                **self._p1,
                CONF_MAX_CHARGE: int(user_input[CONF_MAX_CHARGE]),
                CONF_MAX_DISCHARGE: int(user_input[CONF_MAX_DISCHARGE]),
                SECTION_ADVANCED: _advanced_schema()({}),
            }
            return self.async_create_entry(
                title=data.name,
                data={CONF_HOST: self._host, CONF_START_MODE: user_input[CONF_START_MODE]},
                options=options,
            )

        schema = {
            vol.Required(CONF_START_MODE, default=MODE_SMART): selector.SelectSelector(
                selector.SelectSelectorConfig(options=START_MODES, translation_key=CONF_START_MODE)
            ),
            **_power_schema(data.max_charge_limit, data.max_discharge_limit),
        }
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(schema),
            description_placeholders={"name": data.name},
        )

    # IP-adres veranderd? Via "Opnieuw configureren".
    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            report = await async_probe(async_get_clientsession(self.hass), host, timeout=5)
            if report is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(ZendureData.from_report(report).serial or host)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ZendureLokaalOptionsFlow()


class ZendureLokaalOptionsFlow(OptionsFlow):
    """Instellingen later aanpassen via 'Configureren'."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := _p1_error(self.hass, user_input)) is None:
                return self.async_create_entry(data=user_input)
            errors["base"] = error

        current = entry_settings(self.config_entry)
        coordinator = getattr(self.config_entry, "runtime_data", None)
        device = coordinator.data if coordinator is not None and coordinator.data else None
        max_charge = device.max_charge_limit if device else DEFAULT_MAX_POWER
        max_discharge = device.max_discharge_limit if device else DEFAULT_MAX_POWER

        schema = vol.Schema(
            {
                **_p1_schema(),
                **_power_schema(max_charge, max_discharge),
                vol.Required(SECTION_ADVANCED): section(_advanced_schema(), {"collapsed": True}),
            }
        )
        advanced_keys = [str(key) for key in _advanced_schema().schema]
        suggested: dict[str, Any] = {
            **{k: v for k, v in current.items() if k not in advanced_keys},
            SECTION_ADVANCED: {k: current[k] for k in advanced_keys if k in current},
        }
        if user_input is not None:
            suggested = user_input
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )
