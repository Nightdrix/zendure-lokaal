"""Tests voor de rekenregels van de regelaar (zonder Home Assistant)."""

from __future__ import annotations

import pytest

from custom_components.zendure_lokaal.const import (
    MODE_MANUAL,
    MODE_OFF,
    MODE_SMART,
    MODE_SMART_CHARGING,
    MODE_SMART_DISCHARGING,
    MODE_STORE_SOLAR,
)
from custom_components.zendure_lokaal.regelaar import (
    Meting,
    RegelInstellingen,
    bereken_doel,
    huidige_opdracht,
    moet_schrijven,
    opdracht,
)

S = RegelInstellingen(
    max_charge=2400,
    max_discharge=2400,
    charge_start=300,
    discharge_start=100,
    charge_margin=50,
    discharge_margin=10,
)


def doel(mode: str, **kw) -> int:
    return bereken_doel(mode, Meting(**kw), S)


class TestNulOpDeMeter:
    def test_ontlaadt_bij_verbruik(self) -> None:
        assert doel(MODE_SMART, p1=500, ac_flow=0) == 490

    def test_kleine_vraag_start_niet(self) -> None:
        assert doel(MODE_SMART, p1=80, ac_flow=0) == 0

    def test_kleine_vraag_blijft_wel_doorlopen_als_al_actief(self) -> None:
        # al aan het ontladen met 300 W, huis vraagt nu 80 W extra
        assert doel(MODE_SMART, p1=80, ac_flow=300, current=300) == 370

    def test_laadt_bij_overschot(self) -> None:
        assert doel(MODE_SMART, p1=-1500, ac_flow=0) == -1450

    def test_klein_overschot_start_niet(self) -> None:
        assert doel(MODE_SMART, p1=-200, ac_flow=0) == 0

    def test_blijft_laden_onder_startdrempel(self) -> None:
        # al aan het laden met 1000 W, nog 100 W teruglevering
        assert doel(MODE_SMART, p1=-100, ac_flow=-1000, current=-1000) == -1050

    def test_vol_laadt_niet(self) -> None:
        assert doel(MODE_SMART, p1=-1500, ac_flow=0, full=True) == 0

    def test_leeg_ontlaadt_niet(self) -> None:
        assert doel(MODE_SMART, p1=500, ac_flow=0, empty=True) == 0

    def test_leeg_maar_zon_mag_naar_huis(self) -> None:
        assert doel(MODE_SMART, p1=500, ac_flow=0, empty=True, solar=300) == 300

    def test_begrensd_op_maximum(self) -> None:
        assert doel(MODE_SMART, p1=5000, ac_flow=0) == 2400
        assert doel(MODE_SMART, p1=-5000, ac_flow=0) == -2400

    def test_evenwicht_blijft_stabiel(self) -> None:
        # batterij levert 490 W, meter staat op +10 W: niets veranderen
        assert doel(MODE_SMART, p1=10, ac_flow=490, current=490) == 490

    def test_omslag_laden_naar_verbruik_stopt_eerst(self) -> None:
        # was 1000 W aan het laden, wolk: nu 1050 W afname -> vraag +50 W -> stoppen
        assert doel(MODE_SMART, p1=1050, ac_flow=-1000, current=-1000) == 0


class TestAndereModi:
    def test_slim_ontladen_laadt_nooit(self) -> None:
        assert doel(MODE_SMART_DISCHARGING, p1=-1500, ac_flow=0) == 0

    def test_slim_ontladen_geeft_zon_door(self) -> None:
        assert doel(MODE_SMART_DISCHARGING, p1=-1500, ac_flow=0, solar=600) == 600

    def test_slim_ontladen_ontlaadt(self) -> None:
        assert doel(MODE_SMART_DISCHARGING, p1=700, ac_flow=0) == 690

    def test_slim_laden_ontlaadt_nooit_uit_accu(self) -> None:
        assert doel(MODE_SMART_CHARGING, p1=700, ac_flow=0) == 0

    def test_slim_laden_geeft_zon_door_bij_verbruik(self) -> None:
        assert doel(MODE_SMART_CHARGING, p1=700, ac_flow=0, solar=400) == 400

    def test_slim_laden_laadt(self) -> None:
        assert doel(MODE_SMART_CHARGING, p1=-800, ac_flow=0) == -750

    def test_zon_opslaan_levert_nooit(self) -> None:
        assert doel(MODE_STORE_SOLAR, p1=700, ac_flow=0, solar=400) == 0
        assert doel(MODE_STORE_SOLAR, p1=-800, ac_flow=0) == -750

    def test_uit_doet_niets(self) -> None:
        assert doel(MODE_OFF, p1=700, ac_flow=0) == 0

    @pytest.mark.parametrize(
        ("handmatig", "full", "empty", "verwacht"),
        [
            (800, False, False, 800),
            (-600, False, False, -600),
            (-600, True, False, 0),
            (800, False, True, 0),
            (9999, False, False, 2400),
        ],
    )
    def test_handmatig(self, handmatig: int, full: bool, empty: bool, verwacht: int) -> None:
        m = Meting(p1=0, ac_flow=0, full=full, empty=empty)
        assert bereken_doel(MODE_MANUAL, m, S, handmatig) == verwacht


class TestOpdrachten:
    def test_opdracht(self) -> None:
        assert opdracht(500) == {"smartMode": 1, "acMode": 2, "outputLimit": 500, "inputLimit": 0}
        assert opdracht(-700) == {"smartMode": 1, "acMode": 1, "inputLimit": 700, "outputLimit": 0}
        assert opdracht(0) == {"smartMode": 1, "inputLimit": 0, "outputLimit": 0}

    def test_huidige_opdracht(self) -> None:
        assert huidige_opdracht(2, 0, 400) == 400
        assert huidige_opdracht(1, 300, 0) == -300
        assert huidige_opdracht(2, 300, 0) == 0

    def test_niet_schrijven_als_het_al_klopt(self) -> None:
        assert not moet_schrijven(500, 2, 0, 505, 1)
        assert moet_schrijven(500, 2, 0, 400, 1)
        assert moet_schrijven(500, 1, 0, 500, 1)  # verkeerde AC-modus
        assert moet_schrijven(500, 2, 0, 500, 0)  # in stand-by
        assert not moet_schrijven(0, 2, 0, 0, 0)
        assert moet_schrijven(0, 1, 300, 0, 1)
        assert not moet_schrijven(-700, 1, 695, 0, 1)
