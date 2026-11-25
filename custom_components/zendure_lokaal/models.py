"""Gegevensmodel van een zenSDK-rapport (zonder Home Assistant-code)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Bekende productcodes -> nette naam.
PRODUCT_NAMES: dict[str, str] = {
    "solarflow3000mixac+": "SolarFlow 3000 Mix AC+",
    "solarflow4000mixac+": "SolarFlow 4000 Mix AC+",
    "solarflow4000mixpro": "SolarFlow 4000 Mix Pro",
    "solarflow2400ac": "SolarFlow 2400 AC",
    "solarflow2400ac+": "SolarFlow 2400 AC+",
    "solarflow2400pro": "SolarFlow 2400 Pro",
    "solarflow1600ac+": "SolarFlow 1600 AC+",
    "solarflow800": "SolarFlow 800",
    "solarflow800pro": "SolarFlow 800 Pro",
    "solarflow800pro2": "SolarFlow 800 Pro 2",
    "solarflow800plus": "SolarFlow 800 Plus",
}

# Productseries met een groot ingebouwd accupakket (packType 70 = 8 kWh).
MIX_PRODUCTS = {"solarflow3000mixac+", "solarflow4000mixac+", "solarflow4000mixpro"}


def product_name(product: str | None) -> str:
    """Maak van 'solarFlow3000MixAC+' een leesbare naam."""
    if not product:
        return "Zendure batterij"
    key = product.lower().replace(" ", "")
    if key in PRODUCT_NAMES:
        return PRODUCT_NAMES[key]
    # Onbekend: 'solarFlow1234FooAC+' -> 'SolarFlow 1234 Foo AC+'
    pretty = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Za-z])", " ", product)
    return pretty[:1].upper() + pretty[1:]


def pack_capacity_kwh(pack: dict[str, Any], is_mix: bool) -> float:
    """Schat de capaciteit van één accupakket (kWh)."""
    sn = str(pack.get("sn") or "")
    pack_type = pack.get("packType")
    if pack_type == 70 and is_mix:
        return 8.0
    if sn:
        match sn[0]:
            case "A":
                return 2.4 if len(sn) > 3 and sn[3] == "3" else 0.96
            case "B":
                return 0.96
            case "C":
                return 1.92
            case "F" | "G":
                return 2.88
            case "J":
                return 2.4
    by_type = {5: 2.88, 70: 1.92, 240: 1.92, 250: 0.96, 280: 2.88, 300: 1.92, 350: 2.88, 500: 2.4}
    try:
        return by_type.get(int(pack_type), 0.0)
    except (TypeError, ValueError):
        return 0.0


def deci_kelvin_to_celsius(value: Any) -> float | None:
    """zenSDK geeft temperaturen in tiende Kelvin (2981 = 25,0 °C)."""
    try:
        return round((int(value) - 2731) / 10, 1)
    except (TypeError, ValueError):
        return None


def _num(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ZendureData:
    """Eén momentopname van de batterij."""

    raw: dict[str, Any]
    props: dict[str, Any] = field(default_factory=dict)
    packs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_report(cls, report: dict[str, Any]) -> ZendureData:
        packs = report.get("packData") or []
        if not isinstance(packs, list):
            packs = []
        return cls(raw=report, props=dict(report.get("properties") or {}), packs=packs)

    # --- algemene info -------------------------------------------------------
    @property
    def serial(self) -> str:
        return str(self.raw.get("sn") or "")

    @property
    def product(self) -> str:
        return str(self.raw.get("product") or "")

    @property
    def name(self) -> str:
        return product_name(self.product)

    @property
    def is_mix(self) -> bool:
        return self.product.lower().replace(" ", "") in MIX_PRODUCTS

    def has(self, key: str) -> bool:
        return key in self.props

    def get(self, key: str, default: float = 0) -> float:
        return _num(self.props.get(key), default)

    # --- laadniveau ----------------------------------------------------------
    @property
    def soc(self) -> float:
        return self.get("electricLevel")

    @property
    def soc_max(self) -> float:
        """Maximaal laadniveau in % (batterij geeft x10)."""
        return self.get("socSet", 1000) / 10

    @property
    def soc_min(self) -> float:
        """Minimaal laadniveau in % (batterij geeft x10)."""
        return self.get("minSoc", 0) / 10

    @property
    def soc_limit(self) -> int:
        return int(self.get("socLimit"))

    @property
    def is_full(self) -> bool:
        return self.soc_limit in (1, 17) or self.soc >= self.soc_max

    @property
    def is_empty(self) -> bool:
        return self.soc_limit in (2, 18) or self.soc <= self.soc_min

    @property
    def is_calibrating(self) -> bool:
        return int(self.get("socStatus")) == 1

    # --- vermogens (W) -------------------------------------------------------
    @property
    def home_output(self) -> float:
        """Vermogen dat de batterij aan het huis levert."""
        return self.get("outputHomePower")

    @property
    def grid_input(self) -> float:
        """Vermogen dat de batterij uit het stopcontact haalt."""
        return self.get("gridInputPower")

    @property
    def ac_flow(self) -> float:
        """Netto AC-vermogen: + = levert aan huis, - = haalt van het net."""
        return self.home_output - self.grid_input

    @property
    def charge_power(self) -> float:
        """Vermogen dat de accu in gaat."""
        return self.get("outputPackPower")

    @property
    def discharge_power(self) -> float:
        """Vermogen dat uit de accu komt."""
        return self.get("packInputPower")

    @property
    def battery_power(self) -> float:
        """Netto accuvermogen: + = ontladen, - = laden."""
        return self.discharge_power - self.charge_power

    @property
    def solar_power(self) -> float:
        return max(0.0, self.get("solarInputPower"))

    # --- ingestelde limieten -------------------------------------------------
    @property
    def input_limit(self) -> float:
        return self.get("inputLimit")

    @property
    def output_limit(self) -> float:
        return self.get("outputLimit")

    @property
    def ac_mode(self) -> int:
        return int(self.get("acMode", 0))

    @property
    def smart_mode(self) -> int:
        """1 = instellingen in werkgeheugen (snel bijsturen), 0 = in flash/stand-by."""
        return int(self.get("smartMode", 0))

    @property
    def max_charge_limit(self) -> int:
        value = int(self.get("chargeMaxLimit", 0))
        return value if value > 0 else 2400

    @property
    def max_discharge_limit(self) -> int:
        value = int(self.get("inverseMaxPower", 0))
        return value if value > 0 else 2400

    # --- capaciteit ----------------------------------------------------------
    @property
    def capacity_kwh(self) -> float:
        return round(sum(pack_capacity_kwh(p, self.is_mix) for p in self.packs), 2)

    def apply_write(self, properties: dict[str, Any]) -> None:
        """Verwerk een geschreven instelling direct (optimistisch), tot het volgende rapport."""
        self.props.update(properties)
