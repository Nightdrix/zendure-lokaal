"""Tests voor het instelscherm."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.zendure_lokaal.const import (
    CONF_HOST,
    CONF_MAX_CHARGE,
    CONF_MAX_DISCHARGE,
    CONF_P1_SENSOR,
    CONF_START_MODE,
    DOMAIN,
    SECTION_ADVANCED,
)

from .fake_zendure import FakeZendure

P1 = "sensor.p1_meter_vermogen"


def _p1(hass: HomeAssistant, value: str = "350") -> None:
    hass.states.async_set(P1, value, {"unit_of_measurement": "W", "device_class": "power"})


async def test_volledige_flow_met_ip(hass: HomeAssistant, fake_server: str) -> None:
    _p1(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: fake_server})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "p1"
    assert result["description_placeholders"]["name"] == "SolarFlow 3000 Mix AC+"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_P1_SENSOR: P1})
    assert result["step_id"] == "settings"

    with patch("custom_components.zendure_lokaal.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_START_MODE: "smart", CONF_MAX_CHARGE: 2000, CONF_MAX_DISCHARGE: 800}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SolarFlow 3000 Mix AC+"
    assert result["data"] == {CONF_HOST: fake_server, CONF_START_MODE: "smart"}
    assert result["options"][CONF_P1_SENSOR] == P1
    assert result["options"][CONF_MAX_DISCHARGE] == 800
    assert result["options"][SECTION_ADVANCED]["charge_start"] == 300
    assert result["result"].unique_id == FakeZendure().sn


async def test_half_afgemaakte_poging_blokkeert_niet(hass: HomeAssistant, fake_server: str) -> None:
    _p1(hass)
    eerste = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    eerste = await hass.config_entries.flow.async_configure(eerste["flow_id"], {CONF_HOST: fake_server})
    assert eerste["step_id"] == "p1"  # venster weggeklikt zonder af te ronden

    tweede = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    tweede = await hass.config_entries.flow.async_configure(tweede["flow_id"], {CONF_HOST: fake_server})
    assert tweede["step_id"] == "p1"


async def test_verkeerd_ip_geeft_nette_fout(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "127.0.0.1:1"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_automatisch_zoeken(hass: HomeAssistant, fake_server: str) -> None:
    _p1(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with (
        patch(
            "custom_components.zendure_lokaal.config_flow.hosts_in_networks",
            return_value=["127.0.0.1:1", fake_server],
        ),
        patch("custom_components.zendure_lokaal.config_flow._local_networks", return_value=["x"]),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: ""})
    assert result["step_id"] == "p1"
    assert result["description_placeholders"]["host"] == fake_server


async def test_automatisch_zoeken_niets_gevonden(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.zendure_lokaal.config_flow._local_networks", return_value=[]):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: ""})
    assert result["errors"] == {"base": "not_found"}


async def test_instellingen_later_aanpassen(hass: HomeAssistant, fake_server: str) -> None:
    from .test_integratie import ADVANCED, FakeZendure, koppel

    entry = await koppel(hass, fake_server, FakeZendure())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    nieuw = {**ADVANCED, "charge_start": 150, "standby_minutes": 0}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_P1_SENSOR: P1, CONF_MAX_CHARGE: 1200, CONF_MAX_DISCHARGE: 800, SECTION_ADVANCED: nieuw},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # na herladen gebruikt de regelaar de nieuwe waarden
    coordinator = entry.runtime_data
    assert coordinator.settings["charge_start"] == 150
    assert coordinator.settings[CONF_MAX_DISCHARGE] == 800
    assert coordinator.regel_instellingen(coordinator.data).max_charge == 1200


async def test_ip_adres_wijzigen(hass: HomeAssistant, fake_server: str) -> None:
    from .test_integratie import FakeZendure, koppel

    entry = await koppel(hass, fake_server, FakeZendure())
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "127.0.0.1:1"})
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: fake_server})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_p1_zonder_waarde(hass: HomeAssistant, fake_server: str) -> None:
    _p1(hass, "unavailable")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: fake_server})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_P1_SENSOR: P1})
    assert result["step_id"] == "p1"
    assert result["errors"] == {"base": "p1_no_value"}
