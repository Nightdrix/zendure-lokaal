"""Integratietests: Home Assistant + nep-batterij + P1-meter in een gesloten lus."""

from __future__ import annotations

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from custom_components.zendure_lokaal.const import (
    CONF_HOST,
    CONF_MAX_CHARGE,
    CONF_MAX_DISCHARGE,
    CONF_P1_SENSOR,
    CONF_START_MODE,
    DOMAIN,
    SECTION_ADVANCED,
)
from custom_components.zendure_lokaal.coordinator import ZendureCoordinator

from .fake_zendure import FakeZendure

P1 = "sensor.p1_meter_vermogen"
ADVANCED = {
    "discharge_start": 100,
    "charge_start": 300,
    "discharge_margin": 10,
    "charge_margin": 50,
    "standby_minutes": 15,
    "interval": 5,
    "capacity": 0,
}


def zet_p1(hass: HomeAssistant, fake: FakeZendure) -> None:
    hass.states.async_set(P1, str(round(fake.p1)), {"unit_of_measurement": "W", "device_class": "power"})


async def koppel(hass: HomeAssistant, host: str, fake: FakeZendure, start_mode: str = "smart") -> MockConfigEntry:
    zet_p1(hass, fake)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SolarFlow 3000 Mix AC+",
        unique_id=fake.sn,
        data={CONF_HOST: host, CONF_START_MODE: start_mode},
        options={
            CONF_P1_SENSOR: P1,
            CONF_MAX_CHARGE: 2400,
            CONF_MAX_DISCHARGE: 2400,
            SECTION_ADVANCED: dict(ADVANCED),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def eid(hass: HomeAssistant, platform: str, key: str, serial: str = FakeZendure().sn) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{serial}_{key}")
    assert entity_id, f"{platform}.{key} niet gevonden"
    return entity_id


async def draai(
    hass: HomeAssistant,
    fake: FakeZendure,
    coordinator: ZendureCoordinator,
    stappen: int,
    freezer: FrozenDateTimeFactory,
) -> list[float]:
    """Laat de wereld `stappen` x 5 seconden lopen. Geeft de P1-waarden terug."""
    meter: list[float] = []
    for _ in range(stappen):
        fake.step(5)
        freezer.tick(timedelta(seconds=5))
        zet_p1(hass, fake)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        meter.append(fake.p1)
    return meter


async def test_entiteiten(hass: HomeAssistant, fake: FakeZendure, fake_server: str) -> None:
    await koppel(hass, fake_server, fake)

    assert hass.states.get(eid(hass, "select", "operation")).state == "smart"
    assert hass.states.get(eid(hass, "sensor", "electric_level")).state == "50"
    assert hass.states.get(eid(hass, "number", "soc_set")).state == "100.0"
    assert hass.states.get(eid(hass, "number", "min_soc")).state == "10.0"
    assert hass.states.get(eid(hass, "sensor", "capacity")).state == "10.88"  # 8 kWh + AB3000 (2,88)
    assert hass.states.get(eid(hass, "switch", "pv_export")).state == "on"
    assert hass.states.get(eid(hass, "sensor", "temperature")).state == "25.0"
    assert hass.states.get(eid(hass, "sensor", "pack_soc", "BO4HMIXPACK0001")).state == "50"
    assert hass.states.get(eid(hass, "sensor", "pack_cell_delta", "BO4HMIXPACK0001")).state == "20"
    # Keuzes precies zoals de officiële integratie -> Energienerds-planner werkt ermee
    assert hass.states.get(eid(hass, "select", "operation")).attributes["options"] == [
        "off",
        "manual",
        "smart",
        "smart_discharging",
        "smart_charging",
        "store_solar",
    ]
    assert hass.states.get(eid(hass, "select", "ac_mode")).attributes["options"] == ["input", "output"]


async def test_nul_op_de_meter_ontladen(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 650
    entry = await koppel(hass, fake_server, fake)
    meter = await draai(hass, fake, entry.runtime_data, 6, freezer)

    assert fake.ac_mode == 2
    assert 600 <= fake.output_limit <= 650
    assert 0 <= meter[-1] <= 25, meter
    assert hass.states.get(eid(hass, "sensor", "status")).state == "discharging"


async def test_nul_op_de_meter_laden(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 400
    fake.house_solar = 2000  # 1600 W teruglevering
    entry = await koppel(hass, fake_server, fake)
    meter = await draai(hass, fake, entry.runtime_data, 6, freezer)

    assert fake.ac_mode == 1
    assert 1500 <= fake.input_limit <= 1600
    assert -80 <= meter[-1] <= 0, meter
    assert hass.states.get(eid(hass, "sensor", "status")).state == "charging"


async def test_volgt_wisselend_verbruik_zonder_te_pendelen(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 500
    entry = await koppel(hass, fake_server, fake)
    await draai(hass, fake, entry.runtime_data, 4, freezer)

    fake.house_load = 1800  # waterkoker aan
    meter = await draai(hass, fake, entry.runtime_data, 4, freezer)
    assert 0 <= meter[-1] <= 25, meter

    fake.house_load = 300  # waterkoker uit
    meter = await draai(hass, fake, entry.runtime_data, 4, freezer)
    assert 0 <= meter[-1] <= 25, meter

    # Stabiel verbruik: daarna geen onnodige schrijfacties meer
    fake.writes.clear()
    await draai(hass, fake, entry.runtime_data, 6, freezer)
    assert fake.writes == []


async def test_zonnepanelen_op_de_batterij(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    """3000 Mix met eigen panelen: zon dekt het huis, rest gaat de accu in."""
    fake.house_load = 300
    fake.solar = 900
    entry = await koppel(hass, fake_server, fake)
    meter = await draai(hass, fake, entry.runtime_data, 6, freezer)

    assert 0 <= meter[-1] <= 25, meter
    assert fake.pack_out > 500  # overschot van de panelen gaat de accu in
    assert fake.pack_in == 0  # accu hoeft niet te ontladen


async def test_slim_ontladen_laadt_niet(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_solar = 2000
    entry = await koppel(hass, fake_server, fake)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": eid(hass, "select", "operation"), "option": "smart_discharging"},
        blocking=True,
    )
    await draai(hass, fake, entry.runtime_data, 4, freezer)
    assert fake.input_limit == 0
    assert fake.grid_input == 0


async def test_uit_met_handmatige_knoppen_zoals_de_planner(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    """Planner 'Laden 500 W': modus uit, AC-modus invoer, laadvermogen 500."""
    fake.house_load = 800
    entry = await koppel(hass, fake_server, fake)
    await draai(hass, fake, entry.runtime_data, 3, freezer)
    assert fake.output_limit > 0

    await hass.services.async_call(
        "select", "select_option", {"entity_id": eid(hass, "select", "operation"), "option": "off"}, blocking=True
    )
    assert fake.output_limit == 0 and fake.input_limit == 0  # uitzetten stopt de batterij

    await hass.services.async_call(
        "select", "select_option", {"entity_id": eid(hass, "select", "ac_mode"), "option": "input"}, blocking=True
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid(hass, "number", "input_limit"), "value": 500}, blocking=True
    )
    await draai(hass, fake, entry.runtime_data, 4, freezer)

    assert fake.ac_mode == 1
    assert fake.input_limit == 500  # regelaar blijft er in 'Uit' vanaf
    assert hass.states.get(eid(hass, "number", "input_limit")).state == "500.0"
    assert hass.states.get(eid(hass, "select", "ac_mode")).state == "input"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": eid(hass, "number", "soc_set"), "value": 90}, blocking=True
    )
    assert fake.soc_set == 900


async def test_p1_weg_stopt_veilig_en_hervat(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 700
    entry = await koppel(hass, fake_server, fake)
    coordinator = entry.runtime_data
    await draai(hass, fake, coordinator, 3, freezer)
    assert fake.output_limit > 0

    hass.states.async_set(P1, "unavailable")
    for _ in range(14):
        freezer.tick(timedelta(seconds=5))
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert fake.output_limit == 0
    assert hass.states.get(eid(hass, "sensor", "status")).state == "p1_missing"
    issue_id = f"p1_missing_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    await draai(hass, fake, coordinator, 3, freezer)
    assert fake.output_limit > 0
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_stand_by_na_stilstand(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 50  # te weinig om te ontladen
    fake.smart_mode = 1
    entry = await koppel(hass, fake_server, fake)  # t = 0: stilstand begint
    for _ in range(2):
        freezer.tick(timedelta(minutes=5))
        await draai(hass, fake, entry.runtime_data, 1, freezer)
    freezer.tick(timedelta(minutes=4))
    await draai(hass, fake, entry.runtime_data, 1, freezer)
    assert fake.smart_mode == 1  # 14 minuten: nog niet
    freezer.tick(timedelta(minutes=1))
    await draai(hass, fake, entry.runtime_data, 1, freezer)
    assert fake.smart_mode == 0  # 15 minuten: stand-by
    assert hass.states.get(eid(hass, "sensor", "status")).state == "standby"

    # Verbruik stijgt: batterij wordt weer wakker
    fake.house_load = 600
    await draai(hass, fake, entry.runtime_data, 3, freezer)
    assert fake.smart_mode == 1 and fake.output_limit > 0


async def test_batterij_onbereikbaar(hass: HomeAssistant, fake: FakeZendure, fake_server: str) -> None:
    entry = await koppel(hass, fake_server, fake)
    fake.fail = True
    for _ in range(3):
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, "sensor", "electric_level")).state == "unavailable"

    fake.fail = False
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid(hass, "sensor", "electric_level")).state == "50"


async def test_modus_blijft_bewaard_na_herstart(hass: HomeAssistant, fake: FakeZendure, fake_server: str) -> None:
    mock_restore_cache(hass, [State("select.solarflow_3000_mix_ac_operation_mode", "smart_charging")])
    entry = await koppel(hass, fake_server, fake)
    assert entry.runtime_data.operation == "smart_charging"


async def test_uitschakelen_stopt_batterij(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 700
    entry = await koppel(hass, fake_server, fake)
    await draai(hass, fake, entry.runtime_data, 3, freezer)
    assert fake.output_limit > 0
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert fake.output_limit == 0


async def test_energietellers(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 1000
    entry = await koppel(hass, fake_server, fake)
    await draai(hass, fake, entry.runtime_data, 3, freezer)
    # 1 uur lang ~990 W naar huis
    await draai(hass, fake, entry.runtime_data, 720, freezer)
    value = float(hass.states.get(eid(hass, "sensor", "energy_home")).state)
    assert 0.95 <= value <= 1.05, value


async def test_nederlandse_namen_uit_handleiding(hass: HomeAssistant, fake: FakeZendure, fake_server: str) -> None:
    """De entity-id's die in README.md staan moeten echt zo heten in een Nederlandse HA."""
    hass.config.language = "nl"
    await koppel(hass, fake_server, fake)
    verwacht = {
        ("select", "operation"): "select.solarflow_3000_mix_ac_bedrijfsmodus",
        ("select", "ac_mode"): "select.solarflow_3000_mix_ac_ac_modus",
        ("number", "input_limit"): "number.solarflow_3000_mix_ac_laadvermogen",
        ("number", "output_limit"): "number.solarflow_3000_mix_ac_ontlaadvermogen",
        ("number", "soc_set"): "number.solarflow_3000_mix_ac_maximaal_laadniveau",
        ("number", "min_soc"): "number.solarflow_3000_mix_ac_minimaal_laadniveau",
        ("sensor", "status"): "sensor.solarflow_3000_mix_ac_status",
        ("sensor", "electric_level"): "sensor.solarflow_3000_mix_ac_laadniveau",
        ("sensor", "battery_power"): "sensor.solarflow_3000_mix_ac_accuvermogen_ontladen_laden",
        ("sensor", "p1_power"): "sensor.solarflow_3000_mix_ac_netvermogen_p1",
        ("sensor", "available_energy"): "sensor.solarflow_3000_mix_ac_beschikbare_energie",
    }
    for (platform, key), entity_id in verwacht.items():
        assert eid(hass, platform, key) == entity_id
    assert hass.states.get("select.solarflow_3000_mix_ac_bedrijfsmodus").state == "smart"


async def test_planner_knop_zonder_planner(hass: HomeAssistant, fake: FakeZendure, fake_server: str) -> None:
    from unittest.mock import patch

    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.loader import IntegrationNotFound

    await koppel(hass, fake_server, fake)
    with (
        patch("custom_components.zendure_lokaal.button.async_get_integration", side_effect=IntegrationNotFound("x")),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            "button", "press", {"entity_id": eid(hass, "button", "link_planner")}, blocking=True
        )
    assert err.value.translation_key == "planner_not_installed"


@pytest.mark.parametrize("unit,raw,expected", [("kW", "0.65", 650), ("W", "-1200", -1200)])
async def test_p1_eenheden(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, unit: str, raw: str, expected: float
) -> None:
    entry = await koppel(hass, fake_server, fake)
    hass.states.async_set(P1, raw, {"unit_of_measurement": unit})
    assert entry.runtime_data.read_p1() == pytest.approx(expected)


async def test_trage_p1_meter_schiet_niet_door(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    """P1 die maar eens per 5 s ververst (zoals HomeWizard in HA): geen doorschieten/pendelen."""
    fake.house_load = 300
    entry = await koppel(hass, fake_server, fake)
    coordinator = entry.runtime_data
    await draai(hass, fake, coordinator, 3, freezer)

    fake.house_load = 1500  # grote verbruiker aan
    meter: list[float] = []
    for stap in range(16):
        freezer.tick(timedelta(seconds=2.5))
        fake.step(2.5)
        if stap % 2 == 0:  # meter ververst maar om de 5 seconden
            zet_p1(hass, fake)
        await coordinator.async_refresh()  # tussendoor wél een poll van de batterij
        await hass.async_block_till_done()
        meter.append(fake.p1)

    # Nooit teruglevering door doorschieten, en netjes rond nul uitgekomen
    assert min(meter) >= -5, meter
    assert 0 <= meter[-1] <= 25, meter
    assert 1450 <= fake.output_limit <= 1500
