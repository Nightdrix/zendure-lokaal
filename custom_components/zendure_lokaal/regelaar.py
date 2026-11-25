"""De regelaar: bepaalt hoeveel de batterij moet laden of ontladen.

Werkwijze (zelfde principe als de officiële Zendure-integratie):

    vraag = P1-vermogen + wat de batterij nu aan het huis levert

Dat is wat het huis van het net zou halen als de batterij niets deed.
Is de vraag positief, dan kan de batterij ontladen; is hij negatief (teruglevering),
dan kan de batterij laden. Een start-drempel voorkomt dat de batterij bij elk
klein piekje aan- en uitspringt, en een marge zorgt dat je nooit per ongeluk
accu-stroom terug het net op stuurt of net-stroom gebruikt om te laden.

Uitkomst: één getal in watt. Positief = ontladen (naar huis), negatief = laden.
Dit bestand gebruikt bewust geen Home Assistant-code, zodat het los te testen is.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    MODE_MANUAL,
    MODE_SMART,
    MODE_SMART_CHARGING,
    MODE_SMART_DISCHARGING,
    MODE_STORE_SOLAR,
)

# Kleiner dan dit heeft geen zin: dan gewoon stoppen.
MIN_POWER = 20


@dataclass(frozen=True)
class RegelInstellingen:
    """Instellingen voor de regelaar (alle waarden in watt)."""

    max_charge: int = 2400
    max_discharge: int = 2400
    charge_start: int = 300
    discharge_start: int = 100
    charge_margin: int = 50
    discharge_margin: int = 10


@dataclass(frozen=True)
class Meting:
    """Wat we nu meten."""

    p1: float  # + = afname van het net, - = teruglevering
    ac_flow: float  # + = batterij levert aan huis, - = batterij haalt van net
    solar: float = 0  # zonnepanelen direct op de batterij (W)
    full: bool = False
    empty: bool = False
    current: float = 0  # huidige opdracht: + ontladen, - laden, 0 = niets

    @property
    def vraag(self) -> float:
        """Wat het huis van het net zou halen als de batterij niets deed."""
        return self.p1 + self.ac_flow


def _laden(m: Meting, s: RegelInstellingen) -> int:
    """Laden met overschot. Geeft 0 of een negatief getal."""
    if m.full:
        return 0
    overschot = -m.vraag
    if overschot <= 0:
        return 0
    # Nog niet aan het laden? Dan pas beginnen boven de startdrempel.
    if m.current >= 0 and overschot < s.charge_start:
        return 0
    gewenst = overschot - s.charge_margin
    if gewenst < MIN_POWER:
        return 0
    return -int(min(gewenst, s.max_charge))


def _ontladen(m: Meting, s: RegelInstellingen) -> int:
    """Ontladen naar verbruik. Geeft 0 of een positief getal."""
    if m.empty:
        return _zon_doorgeven(m, s)
    vraag = m.vraag
    if vraag <= 0:
        return 0
    # Nog niet aan het ontladen? Dan pas beginnen boven de startdrempel.
    if m.current <= 0 and vraag < s.discharge_start:
        return 0
    gewenst = vraag - s.discharge_margin
    if gewenst < MIN_POWER:
        return 0
    return int(min(gewenst, s.max_discharge))


def _zon_doorgeven(m: Meting, s: RegelInstellingen) -> int:
    """Alleen zonnestroom van de batterij-panelen naar het huis (accu niet gebruiken)."""
    if m.solar < MIN_POWER or m.vraag <= 0:
        return 0
    gewenst = min(m.vraag - s.discharge_margin, m.solar)
    if gewenst < MIN_POWER:
        return 0
    return int(min(gewenst, s.max_discharge))


def bereken_doel(
    mode: str,
    meting: Meting,
    inst: RegelInstellingen,
    handmatig: float = 0,
) -> int:
    """Bereken het gewenste vermogen (+ ontladen, - laden) voor deze modus."""
    if mode == MODE_SMART:
        # Nul op de meter: laden bij overschot, ontladen bij verbruik.
        if meting.vraag > 0:
            return _ontladen(meting, inst)
        return _laden(meting, inst)

    if mode == MODE_SMART_DISCHARGING:
        # Slim ontladen: alleen ontladen, nooit laden. Zonnestroom gaat altijd door.
        doel = _ontladen(meting, inst) if meting.vraag > 0 else 0
        zon = int(min(meting.solar, inst.max_discharge)) if meting.solar >= MIN_POWER else 0
        return max(doel, zon)

    if mode == MODE_SMART_CHARGING:
        # Slim laden: alleen laden met overschot. Bij verbruik mag zonnestroom door.
        if meting.vraag < 0:
            return _laden(meting, inst)
        return _zon_doorgeven(meting, inst)

    if mode == MODE_STORE_SOLAR:
        # Alleen zonne-energie opslaan: alleen laden, nooit leveren.
        return _laden(meting, inst) if meting.vraag < 0 else 0

    if mode == MODE_MANUAL:
        doel = int(max(-inst.max_charge, min(inst.max_discharge, handmatig)))
        if doel < 0 and meting.full:
            return 0
        if doel > 0 and meting.empty:
            return 0
        if abs(doel) < MIN_POWER:
            return 0
        return doel

    return 0


def opdracht(doel: int) -> dict[str, int]:
    """Vertaal het doel naar de instellingen die naar de batterij gaan.

    smartMode 1 = instellingen alleen in werkgeheugen; zo slijt het flashgeheugen
    van de batterij niet door het vele bijsturen.
    """
    if doel > 0:
        return {"smartMode": 1, "acMode": 2, "outputLimit": int(doel), "inputLimit": 0}
    if doel < 0:
        return {"smartMode": 1, "acMode": 1, "inputLimit": int(-doel), "outputLimit": 0}
    return {"smartMode": 1, "inputLimit": 0, "outputLimit": 0}


STANDBY_OPDRACHT = {"smartMode": 0, "inputLimit": 0, "outputLimit": 0}


def huidige_opdracht(ac_mode: int, input_limit: float, output_limit: float) -> int:
    """Wat staat er nu ingesteld op de batterij (+ ontladen, - laden)."""
    if ac_mode == 2 and output_limit > 0:
        return int(output_limit)
    if ac_mode == 1 and input_limit > 0:
        return -int(input_limit)
    return 0


def moet_schrijven(
    doel: int,
    ac_mode: int,
    input_limit: float,
    output_limit: float,
    smart_mode: int,
    drempel: int = 10,
) -> bool:
    """Alleen schrijven als het echt verschilt van wat er al ingesteld staat."""
    if doel == 0:
        return input_limit != 0 or output_limit != 0
    if smart_mode != 1:
        return True
    if doel > 0:
        return ac_mode != 2 or input_limit != 0 or abs(output_limit - doel) >= drempel
    return ac_mode != 1 or output_limit != 0 or abs(input_limit + doel) >= drempel
