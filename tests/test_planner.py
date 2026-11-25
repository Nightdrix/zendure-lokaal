"""Samenwerking met de échte Energienerds-planner (zendure_schedule).

Draait alleen als ZENDURE_SCHEDULE_SRC naar de planner-code wijst (zie conftest.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.zendure_lokaal.const import DOMAIN

from .conftest import PLANNER_AVAILABLE
from .fake_zendure import FakeZendure
from .test_integratie import draai, eid, koppel

pytestmark = pytest.mark.skipif(not PLANNER_AVAILABLE, reason="planner-code niet beschikbaar")


async def _zet_uur(hass: HomeAssistant, slot: dict) -> None:
    """Zet in de planner het huidige uur op `slot` (zoals de kaart dat doet)."""
    from custom_components.zendure_schedule.schedule import normalize_schedule, serialize_compact

    hours = normalize_schedule(None, 500, charge_soc=100, discharge_soc=10)
    hours[dt_util.now().hour] = slot
    raw = serialize_compact(True, hours, 500, charge_soc=100, discharge_soc=10)
    await hass.services.async_call("zendure_schedule", "set_schedule", {"value": raw}, blocking=True)
    await hass.async_block_till_done()


async def test_planner_koppelen_en_aansturen(
    hass: HomeAssistant, fake: FakeZendure, fake_server: str, freezer: FrozenDateTimeFactory
) -> None:
    fake.house_load = 700
    entry = await koppel(hass, fake_server, fake)
    coordinator = entry.runtime_data
    await draai(hass, fake, coordinator, 3, freezer)
    assert fake.output_limit > 0

    with patch("custom_components.zendure_schedule.async_register_frontend", AsyncMock()):
        # 1. Eén klik op de knop koppelt de planner
        await hass.services.async_call(
            "button", "press", {"entity_id": eid(hass, "button", "link_planner")}, blocking=True
        )
        await hass.async_block_till_done()

        planners = hass.config_entries.async_entries("zendure_schedule")
        assert len(planners) == 1
        data = planners[0].data
        assert data["operation_entity"] == eid(hass, "select", "operation")
        assert data["direction_entity"] == eid(hass, "select", "ac_mode")
        assert data["charge_power_entity"] == eid(hass, "number", "input_limit")
        assert data["discharge_power_entity"] == eid(hass, "number", "output_limit")
        assert data["charge_soc_entity"] == eid(hass, "number", "soc_set")
        assert data["discharge_soc_entity"] == eid(hass, "number", "min_soc")

        # Lege planning = alle uren 'Uit': planner zet onze modus op uit en de batterij stil
        assert hass.states.get(eid(hass, "select", "operation")).state == "off"
        assert fake.output_limit == 0 and fake.input_limit == 0

        # 2. Planner: dit uur laden met 500 W tot 90%
        await _zet_uur(hass, {"mode": "charge", "power": 500, "soc": 90, "soc_min": 0})
        assert fake.ac_mode == 1
        assert fake.input_limit == 500
        assert fake.output_limit == 0
        assert fake.soc_set == 900
        await draai(hass, fake, coordinator, 3, freezer)
        assert fake.input_limit == 500  # onze regelaar laat de planner met rust

        # 3. Planner: dit uur ontladen met 800 W tot 20%
        await _zet_uur(hass, {"mode": "discharge", "power": 800, "soc": 20, "soc_min": 0})
        assert fake.ac_mode == 2
        assert fake.output_limit == 800
        assert fake.input_limit == 0
        assert fake.min_soc == 200

        # 4. Planner: dit uur Nul op de meter (max 100%, min 15%)
        await _zet_uur(hass, {"mode": "nom", "power": 500, "soc": 100, "soc_min": 15})
        assert hass.states.get(eid(hass, "select", "operation")).state == "smart"
        assert fake.soc_set == 1000 and fake.min_soc == 150
        meter = await draai(hass, fake, coordinator, 5, freezer)
        assert 0 <= meter[-1] <= 25, meter

        # 5. Planner: Slim laden
        await _zet_uur(hass, {"mode": "nom_l", "power": 500, "soc": 100, "soc_min": 10})
        assert hass.states.get(eid(hass, "select", "operation")).state == "smart_charging"
        await draai(hass, fake, coordinator, 3, freezer)
        assert fake.output_limit == 0  # slim laden ontlaadt de accu niet

        # 6. Nog een keer koppelen geeft een nette melding
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "button", "press", {"entity_id": eid(hass, "button", "link_planner")}, blocking=True
            )

        for planner in planners:
            await hass.config_entries.async_unload(planner.entry_id)
    assert DOMAIN in hass.config.components
