"""Sensoren: laadniveau, vermogens, energie-tellers en accupakketten."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER, STATUSES
from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureEntity
from .models import ZendureData, deci_kelvin_to_celsius

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ZendureSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ZendureCoordinator], Any]
    exists_fn: Callable[[ZendureData], bool] = lambda _: True


def _available_kwh(c: ZendureCoordinator) -> float:
    d = c.data
    return round(max(0.0, d.soc - d.soc_min) / 100 * c.capacity_kwh, 2)


def _remaining_hours(c: ZendureCoordinator) -> float:
    d = c.data
    if d.discharge_power >= 10:
        return round(_available_kwh(c) * 1000 / d.discharge_power, 1)
    if d.charge_power >= 10:
        to_full = max(0.0, d.soc_max - d.soc) / 100 * c.capacity_kwh
        return round(to_full * 1000 / d.charge_power, 1)
    return 0


def _has(key: str) -> Callable[[ZendureData], bool]:
    return lambda d: d.has(key)


def _power(key: str, translation_key: str, **kwargs: Any) -> ZendureSensorDescription:
    return ZendureSensorDescription(
        key=translation_key,
        translation_key=translation_key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.data.get(key),
        exists_fn=_has(key),
        **kwargs,
    )


SENSORS: tuple[ZendureSensorDescription, ...] = (
    ZendureSensorDescription(
        key="electric_level",
        translation_key="electric_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: round(c.data.soc),
    ),
    ZendureSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUSES,
        value_fn=lambda c: c.status,
    ),
    ZendureSensorDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.data.battery_power,
    ),
    _power("outputPackPower", "charge_power", icon="mdi:battery-plus"),
    _power("packInputPower", "discharge_power", icon="mdi:battery-minus"),
    _power("outputHomePower", "home_output", icon="mdi:home-import-outline"),
    _power("gridInputPower", "grid_input", icon="mdi:transmission-tower-export"),
    _power("solarInputPower", "solar_power", icon="mdi:solar-power"),
    *(
        _power(f"solarPower{i}", f"solar_power_{i}", icon="mdi:solar-panel", entity_registry_enabled_default=False)
        for i in range(1, 7)
    ),
    _power("gridOffPower", "offgrid_power", icon="mdi:power-socket-eu"),
    ZendureSensorDescription(
        key="target_power",
        translation_key="target_power",
        icon="mdi:target",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.target,
    ),
    ZendureSensorDescription(
        key="p1_power",
        translation_key="p1_power",
        icon="mdi:meter-electric-outline",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: None if c.p1_value is None else round(c.p1_value),
    ),
    ZendureSensorDescription(
        key="available_energy",
        translation_key="available_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_available_kwh,
    ),
    ZendureSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        icon="mdi:timer-sand",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=_remaining_hours,
    ),
    ZendureSensorDescription(
        key="capacity",
        translation_key="capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda c: c.capacity_kwh,
    ),
    ZendureSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: deci_kelvin_to_celsius(c.data.props.get("hyperTmp")),
        exists_fn=_has("hyperTmp"),
    ),
    ZendureSensorDescription(
        key="max_charge_limit",
        translation_key="max_charge_limit",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.max_charge_limit,
    ),
    ZendureSensorDescription(
        key="max_discharge_limit",
        translation_key="max_discharge_limit",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.max_discharge_limit,
    ),
    ZendureSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda c: round(c.data.get("BatVolt") / 100, 2),
        exists_fn=_has("BatVolt"),
    ),
    ZendureSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.get("rssi"),
        exists_fn=_has("rssi"),
    ),
    ZendureSensorDescription(
        key="pack_count",
        translation_key="pack_count",
        icon="mdi:layers-triple",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: int(c.data.get("packNum", len(c.data.packs))),
    ),
)


@dataclass(frozen=True, kw_only=True)
class EnergyDescription(SensorEntityDescription):
    """Energieteller: telt een vermogen op tot kWh (voor het Energie-dashboard)."""

    power_fn: Callable[[ZendureData], float]
    exists_fn: Callable[[ZendureData], bool] = lambda _: True


ENERGY: tuple[EnergyDescription, ...] = (
    EnergyDescription(key="energy_charged", translation_key="energy_charged", power_fn=lambda d: d.charge_power),
    EnergyDescription(
        key="energy_discharged", translation_key="energy_discharged", power_fn=lambda d: d.discharge_power
    ),
    EnergyDescription(key="energy_home", translation_key="energy_home", power_fn=lambda d: d.home_output),
    EnergyDescription(key="energy_grid", translation_key="energy_grid", power_fn=lambda d: d.grid_input),
    EnergyDescription(
        key="energy_solar",
        translation_key="energy_solar",
        power_fn=lambda d: d.solar_power,
        exists_fn=_has("solarInputPower"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data
    entities: list[SensorEntity] = [ZendureSensor(coordinator, d) for d in SENSORS if d.exists_fn(data)]
    entities.extend(ZendureEnergySensor(coordinator, d) for d in ENERGY if d.exists_fn(data))
    for index, pack in enumerate(data.packs, start=1):
        if sn := pack.get("sn"):
            entities.extend(PackSensor(coordinator, str(sn), index, d) for d in PACK_SENSORS if d.key_present(pack))
    async_add_entities(entities)


class ZendureSensor(ZendureEntity, SensorEntity):
    entity_description: ZendureSensorDescription

    def __init__(self, coordinator: ZendureCoordinator, description: ZendureSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)


class ZendureEnergySensor(ZendureEntity, RestoreSensor):
    """Telt vermogen op tot kWh (trapeziumregel). Blijft bewaard na herstart."""

    entity_description: EnergyDescription
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    # Gat langer dan dit (bijv. HA was uit)? Dan niet bijtellen.
    MAX_GAP_SECONDS = 300

    def __init__(self, coordinator: ZendureCoordinator, description: EnergyDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._total = 0.0
        self._last_time: datetime | None = None
        self._last_power: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            try:
                self._total = float(last.native_value or 0)
            except (TypeError, ValueError):
                self._total = 0.0

    @property
    def native_value(self) -> float:
        return round(self._total, 3)

    @callback
    def _handle_coordinator_update(self) -> None:
        now = dt_util.utcnow()
        power = max(0.0, self.entity_description.power_fn(self.coordinator.data))
        if self._last_time is not None and self._last_power is not None:
            seconds = (now - self._last_time).total_seconds()
            if 0 < seconds <= self.MAX_GAP_SECONDS:
                self._total += (self._last_power + power) / 2 * seconds / 3_600_000
        self._last_time = now
        self._last_power = power
        super()._handle_coordinator_update()


# ----------------------------------------------------------------- accupakketten
@dataclass(frozen=True, kw_only=True)
class PackSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    required: tuple[str, ...] = ()

    def key_present(self, pack: dict[str, Any]) -> bool:
        return all(k in pack for k in self.required)


def _cell_delta_mv(pack: dict[str, Any]) -> float | None:
    try:
        return round((float(pack["maxVol"]) - float(pack["minVol"])) * 10)
    except (KeyError, TypeError, ValueError):
        return None


PACK_SENSORS: tuple[PackSensorDescription, ...] = (
    PackSensorDescription(
        key="pack_soc",
        translation_key="pack_soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: p.get("socLevel"),
        required=("socLevel",),
    ),
    PackSensorDescription(
        key="pack_temperature",
        translation_key="pack_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: deci_kelvin_to_celsius(p.get("maxTemp")),
        required=("maxTemp",),
    ),
    PackSensorDescription(
        key="pack_power",
        translation_key="pack_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda p: p.get("power"),
        required=("power",),
    ),
    PackSensorDescription(
        key="pack_cell_delta",
        translation_key="pack_cell_delta",
        icon="mdi:battery-heart-variant",
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_cell_delta_mv,
        required=("maxVol", "minVol"),
    ),
    PackSensorDescription(
        key="pack_voltage",
        translation_key="pack_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda p: round(float(p.get("totalVol", 0)) / 100, 2),
        required=("totalVol",),
    ),
)


class PackSensor(ZendureEntity, SensorEntity):
    """Sensor van één accupakket (eigen apparaat, onder de batterij)."""

    entity_description: PackSensorDescription

    def __init__(
        self,
        coordinator: ZendureCoordinator,
        pack_sn: str,
        index: int,
        description: PackSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._pack_sn = pack_sn
        self._attr_unique_id = f"{pack_sn}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pack_sn)},
            name=f"{coordinator.data.name} accu {index}",
            manufacturer=MANUFACTURER,
            model="Accupakket",
            serial_number=pack_sn,
            via_device=(DOMAIN, coordinator.serial),
        )

    def _pack(self) -> dict[str, Any] | None:
        for pack in self.coordinator.data.packs:
            if str(pack.get("sn")) == self._pack_sn:
                return pack
        return None

    @property
    def available(self) -> bool:
        return super().available and self._pack() is not None

    @property
    def native_value(self) -> Any:
        pack = self._pack()
        return None if pack is None else self.entity_description.value_fn(pack)
